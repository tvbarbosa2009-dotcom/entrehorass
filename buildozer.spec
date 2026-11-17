[app]
title = Lembretes
package.name = lembretes
package.domain = org.thiago
source.dir = .
source.include_exts = py,png,jpg,kv,wav,json
version = 0.1
requirements = python3,kivy,plyer
orientation = portrait
fullscreen = 0

# Permissões do Android
android.permissions = VIBRATE,WAKE_LOCK,POST_NOTIFICATIONS
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 0
