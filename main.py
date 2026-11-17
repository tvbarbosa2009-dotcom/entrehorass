"""
Lembretes de Medicamentos - protótipo em Python + Kivy

O que o app faz:
- Cadastra remédios com nome e horário (HH:MM)
- Mostra o próximo remédio do dia em destaque
- Na hora certa: toca um som, vibra e mostra um aviso grande
  com os botões "TOMEI" e "ADIAR 5 MIN"
- Salva tudo em um arquivo, então os remédios continuam lá
  quando você fecha e abre o app

IMPORTANTE: nesta versão o alarme só toca com o app ABERTO.
Para tocar com o celular bloqueado, é preciso um serviço em
segundo plano (veja as notas na conversa).
"""

import json
import math
import os
import struct
import wave
from datetime import datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

# Cores com alto contraste (R, G, B, transparência)
FUNDO = (1, 1, 1, 1)
TEXTO = (0, 0, 0, 1)
AZUL = (0.05, 0.25, 0.65, 1)
VERDE = (0.05, 0.45, 0.15, 1)
VERMELHO = (0.65, 0.08, 0.08, 1)
CINZA = (0.92, 0.92, 0.92, 1)

Window.clearcolor = FUNDO


def vibrar(segundos=1.0):
    """Vibra o aparelho. No computador não faz nada."""
    try:
        from plyer import vibrator
        vibrator.vibrate(time=segundos)
    except Exception:
        pass  # sem vibrador (ex.: rodando no PC)


def criar_som_alarme(caminho):
    """Gera um 'bip-bip' em arquivo .wav se ele ainda não existir."""
    if os.path.exists(caminho):
        return
    taxa = 22050
    quadros = bytearray()
    for _ in range(2):  # dois bipes
        for i in range(int(taxa * 0.25)):
            valor = int(20000 * math.sin(2 * math.pi * 880 * i / taxa))
            quadros += struct.pack("<h", valor)
        quadros += struct.pack("<h", 0) * int(taxa * 0.15)  # pausa
    quadros += struct.pack("<h", 0) * int(taxa * 0.5)
    with wave.open(caminho, "wb") as arq:
        arq.setnchannels(1)
        arq.setsampwidth(2)
        arq.setframerate(taxa)
        arq.writeframes(bytes(quadros))


class BotaoGrande(Button):
    """Botão grande e legível (acessibilidade)."""

    def __init__(self, cor=AZUL, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(56)
        self.font_size = sp(20)
        self.bold = True
        self.background_normal = ""
        self.background_color = cor
        self.color = (1, 1, 1, 1)


class Rotulo(Label):
    def __init__(self, tamanho=20, **kwargs):
        super().__init__(**kwargs)
        self.font_size = sp(tamanho)
        self.color = TEXTO
        self.halign = "left"
        self.valign = "middle"
        self.bind(size=lambda w, _: setattr(w, "text_size", w.size))


class LembretesApp(App):
    title = "Lembretes de Medicamentos"

    # ---------- Início ----------
    def build(self):
        self.arquivo = os.path.join(self.user_data_dir, "remedios.json")
        self.remedios = self.carregar()
        self.adiados = []  # lista de (nome, datetime em que deve tocar)
        self.alarme_aberto = None
        self.som = None
        self.evento_vibracao = None

        som_path = os.path.join(self.user_data_dir, "alarme.wav")
        criar_som_alarme(som_path)
        self.som = SoundLoader.load(som_path)
        if self.som:
            self.som.loop = True

        raiz = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))

        # Destaque: próximo remédio
        self.lbl_proximo = Label(
            text="", font_size=sp(24), bold=True, color=AZUL,
            size_hint_y=None, height=dp(90), halign="center", valign="middle",
        )
        self.lbl_proximo.bind(
            size=lambda w, _: setattr(w, "text_size", w.size))
        raiz.add_widget(self.lbl_proximo)

        # Lista de remédios
        self.lista = BoxLayout(orientation="vertical", spacing=dp(8),
                               size_hint_y=None)
        self.lista.bind(minimum_height=self.lista.setter("height"))
        rolagem = ScrollView()
        rolagem.add_widget(self.lista)
        raiz.add_widget(rolagem)

        # Formulário de cadastro
        self.entrada_nome = TextInput(
            hint_text="Nome do remédio", multiline=False,
            font_size=sp(20), size_hint_y=None, height=dp(56))
        self.entrada_hora = TextInput(
            hint_text="Horário (ex.: 08:30)", multiline=False,
            font_size=sp(20), size_hint_y=None, height=dp(56),
            input_filter=lambda texto, _: texto if (texto.isdigit() or texto == ":") else "")
        self.lbl_erro = Label(text="", color=VERMELHO, font_size=sp(16),
                              size_hint_y=None, height=dp(24))
        raiz.add_widget(self.entrada_nome)
        raiz.add_widget(self.entrada_hora)
        raiz.add_widget(self.lbl_erro)
        raiz.add_widget(BotaoGrande(text="ADICIONAR REMÉDIO", cor=VERDE,
                                    on_release=self.adicionar))

        self.atualizar_tela()
        Clock.schedule_interval(self.verificar_horarios, 1)
        return raiz

    # ---------- Salvar e carregar ----------
    def carregar(self):
        try:
            with open(self.arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def salvar(self):
        with open(self.arquivo, "w", encoding="utf-8") as f:
            json.dump(self.remedios, f, ensure_ascii=False, indent=2)

    # ---------- Cadastro ----------
    def adicionar(self, *_):
        nome = self.entrada_nome.text.strip()
        hora = self.entrada_hora.text.strip()
        try:
            hora = datetime.strptime(hora, "%H:%M").strftime("%H:%M")
        except ValueError:
            self.lbl_erro.text = "Horário inválido. Use HH:MM, ex.: 08:30"
            return
        if not nome:
            self.lbl_erro.text = "Digite o nome do remédio."
            return
        self.remedios.append({"nome": nome, "hora": hora, "ultimo_aviso": ""})
        self.remedios.sort(key=lambda r: r["hora"])
        self.salvar()
        self.entrada_nome.text = ""
        self.entrada_hora.text = ""
        self.lbl_erro.text = ""
        self.atualizar_tela()

    def apagar(self, remedio, *_):
        self.remedios.remove(remedio)
        self.salvar()
        self.atualizar_tela()

    # ---------- Tela ----------
    def atualizar_tela(self):
        self.lista.clear_widgets()
        if not self.remedios:
            self.lista.add_widget(Rotulo(
                text="Nenhum remédio cadastrado ainda.",
                size_hint_y=None, height=dp(56)))
        for r in self.remedios:
            linha = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(8))
            linha.add_widget(Rotulo(text=f"[b]{r['hora']}[/b]  {r['nome']}",
                                    markup=True, tamanho=22))
            btn = BotaoGrande(text="APAGAR", cor=VERMELHO,
                              size_hint_x=None, width=dp(110))
            btn.bind(on_release=lambda _, rem=r: self.apagar(rem))
            linha.add_widget(btn)
            self.lista.add_widget(linha)
        self.atualizar_proximo()

    def atualizar_proximo(self):
        if not self.remedios:
            self.lbl_proximo.text = "Cadastre seu primeiro remédio"
            return
        agora = datetime.now()
        candidatos = []
        for r in self.remedios:
            h, m = map(int, r["hora"].split(":"))
            quando = agora.replace(hour=h, minute=m, second=0, microsecond=0)
            if quando < agora:
                quando += timedelta(days=1)
            candidatos.append((quando, r))
        quando, r = min(candidatos, key=lambda c: c[0])
        dia = "hoje" if quando.date() == agora.date() else "amanhã"
        self.lbl_proximo.text = (
            f"Próximo: {r['nome']}\n{quando.strftime('%H:%M')} ({dia})")

    # ---------- Alarme ----------
    def verificar_horarios(self, _dt):
        """Roda a cada segundo e confere se chegou a hora de algum remédio."""
        if self.alarme_aberto:
            return  # já tem um alarme na tela
        agora = datetime.now()
        marca = agora.strftime("%Y-%m-%d %H:%M")

        # 1) Horários normais
        for r in self.remedios:
            if r["hora"] == agora.strftime("%H:%M") and r["ultimo_aviso"] != marca:
                r["ultimo_aviso"] = marca
                self.salvar()
                self.disparar_alarme(r["nome"])
                return

        # 2) Remédios adiados
        for item in list(self.adiados):
            nome, quando = item
            if agora >= quando:
                self.adiados.remove(item)
                self.disparar_alarme(nome)
                return

        if agora.second == 0:
            self.atualizar_proximo()

    def disparar_alarme(self, nome):
        if self.som:
            self.som.play()
        vibrar(1.0)
        self.evento_vibracao = Clock.schedule_interval(
            lambda _dt: vibrar(1.0), 2)

        conteudo = BoxLayout(orientation="vertical", padding=dp(16),
                             spacing=dp(12))
        conteudo.add_widget(Label(
            text=f"Hora de tomar:\n[b]{nome}[/b]", markup=True,
            font_size=sp(28), color=TEXTO, halign="center"))
        conteudo.add_widget(BotaoGrande(
            text="TOMEI", cor=VERDE, height=dp(72),
            on_release=lambda *_: self.encerrar_alarme()))
        conteudo.add_widget(BotaoGrande(
            text="ADIAR 5 MIN", cor=AZUL, height=dp(72),
            on_release=lambda *_: self.encerrar_alarme(adiar_nome=nome)))

        self.alarme_aberto = Popup(
            title="LEMBRETE", content=conteudo, auto_dismiss=False,
            size_hint=(0.92, 0.7), title_size=sp(22),
            background_color=CINZA)
        self.alarme_aberto.open()

    def encerrar_alarme(self, adiar_nome=None):
        if self.som:
            self.som.stop()
        if self.evento_vibracao:
            self.evento_vibracao.cancel()
            self.evento_vibracao = None
        if self.alarme_aberto:
            self.alarme_aberto.dismiss()
            self.alarme_aberto = None
        if adiar_nome:
            self.adiados.append(
                (adiar_nome, datetime.now() + timedelta(minutes=5)))
        self.atualizar_proximo()


if __name__ == "__main__":
    LembretesApp().run()
