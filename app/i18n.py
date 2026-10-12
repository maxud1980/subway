"""UI localization and persistent interface preferences for Subway."""
from __future__ import annotations

import json
import os
from pathlib import Path

UI_LANGUAGES = {
    "English": "en",
    "Deutsch": "de",
    "Français": "fr",
    "Español": "es",
    "Українська": "uk",
}

DEFAULT_LANGUAGE = "English"

# Keys are the original English UI strings. Missing entries intentionally fall back to English.
TEXT = {
    "en": {},
    "de": {
        "Local subtitle generator": "Lokaler Untertitelgenerator",
        "Recognition model": "Erkennungsmodell",
        "Download model": "Modell herunterladen",
        "Model ready": "Modell bereit",
        "1. Create subtitles": "1. Untertitel erstellen",
        "No media file selected": "Keine Medien-Datei ausgewählt",
        "Select video or audio": "Video oder Audio auswählen",
        "Create SRT": "SRT erstellen",
        "2. Optional translation": "2. Optionale Übersetzung",
        "Provider": "Anbieter",
        "Target language": "Zielsprache",
        "Model": "Modell",
        "API key (encrypted)": "API-Schlüssel (verschlüsselt)",
        "No SRT selected": "Keine SRT-Datei ausgewählt",
        "Select SRT": "SRT auswählen",
        "Translate SRT": "SRT übersetzen",
        "Status": "Status",
        "Ready. Select a local media file to begin.": "Bereit. Wähle eine lokale Medien-Datei aus.",
        "Settings": "Einstellungen",
        "About": "Über",
        "Author": "Autor",
        "Interface language": "Oberflächensprache",
        "Choose the language used by the application.": "Wähle die Sprache der Anwendung.",
        "Check for updates": "Nach Updates suchen",
        "Check whether a newer Subway version is available.": "Prüfen, ob eine neuere Subway-Version verfügbar ist.",
        "Current version": "Aktuelle Version",
        "Latest version": "Neueste Version",
        "GitHub repository": "GitHub-Repository",
        "Close": "Schließen",
        "Checking for updates…": "Suche nach Updates…",
        "Open the release page?": "Release-Seite öffnen?",
        "Update available": "Update verfügbar",
        "You are using the latest version.": "Du verwendest die neueste Version.",
        "No published releases were found.": "Es wurden keine veröffentlichten Versionen gefunden.",
        "Could not check for updates. Check your internet connection and try again.": "Updates konnten nicht geprüft werden. Prüfe deine Internetverbindung.",
        "Select a video or audio file first.": "Wähle zuerst eine Video- oder Audiodatei aus.",
        "Download the selected recognition model first.": "Lade zuerst das ausgewählte Erkennungsmodell herunter.",
        "Enter an API key first.": "Gib zuerst einen API-Schlüssel ein.",
        "SRT created successfully.": "SRT erfolgreich erstellt.",
        "Translated SRT created successfully.": "Übersetzte SRT erfolgreich erstellt.",
        "Ready": "Bereit",
    },
    "fr": {
        "Local subtitle generator": "Générateur de sous-titres local",
        "Recognition model": "Modèle de reconnaissance",
        "Download model": "Télécharger le modèle",
        "Model ready": "Modèle prêt",
        "1. Create subtitles": "1. Créer des sous-titres",
        "No media file selected": "Aucun fichier média sélectionné",
        "Select video or audio": "Choisir une vidéo ou un audio",
        "Create SRT": "Créer un SRT",
        "2. Optional translation": "2. Traduction facultative",
        "Provider": "Fournisseur",
        "Target language": "Langue cible",
        "Model": "Modèle",
        "API key (encrypted)": "Clé API (chiffrée)",
        "No SRT selected": "Aucun SRT sélectionné",
        "Select SRT": "Choisir un SRT",
        "Translate SRT": "Traduire le SRT",
        "Status": "État",
        "Ready. Select a local media file to begin.": "Prêt. Sélectionnez un fichier média local pour commencer.",
        "Settings": "Paramètres",
        "About": "À propos",
        "Author": "Auteur",
        "Interface language": "Langue de l’interface",
        "Choose the language used by the application.": "Choisissez la langue de l’application.",
        "Check for updates": "Rechercher des mises à jour",
        "Check whether a newer Subway version is available.": "Vérifier si une version plus récente de Subway est disponible.",
        "Current version": "Version actuelle",
        "Latest version": "Dernière version",
        "GitHub repository": "Dépôt GitHub",
        "Close": "Fermer",
        "Checking for updates…": "Recherche des mises à jour…",
        "Open the release page?": "Ouvrir la page de la version publiée ?",
        "Update available": "Mise à jour disponible",
        "You are using the latest version.": "Vous utilisez la dernière version.",
        "No published releases were found.": "Aucune version publiée n’a été trouvée.",
        "Could not check for updates. Check your internet connection and try again.": "Impossible de vérifier les mises à jour. Vérifiez votre connexion Internet.",
        "Select a video or audio file first.": "Sélectionnez d’abord un fichier vidéo ou audio.",
        "Download the selected recognition model first.": "Téléchargez d’abord le modèle de reconnaissance sélectionné.",
        "Enter an API key first.": "Saisissez d’abord une clé API.",
        "SRT created successfully.": "SRT créé avec succès.",
        "Translated SRT created successfully.": "SRT traduit créé avec succès.",
        "Ready": "Prêt",
    },
    "es": {
        "Local subtitle generator": "Generador local de subtítulos",
        "Recognition model": "Modelo de reconocimiento",
        "Download model": "Descargar modelo",
        "Model ready": "Modelo listo",
        "1. Create subtitles": "1. Crear subtítulos",
        "No media file selected": "No hay ningún archivo multimedia seleccionado",
        "Select video or audio": "Seleccionar vídeo o audio",
        "Create SRT": "Crear SRT",
        "2. Optional translation": "2. Traducción opcional",
        "Provider": "Proveedor",
        "Target language": "Idioma de destino",
        "Model": "Modelo",
        "API key (encrypted)": "Clave API (cifrada)",
        "No SRT selected": "No hay ningún SRT seleccionado",
        "Select SRT": "Seleccionar SRT",
        "Translate SRT": "Traducir SRT",
        "Status": "Estado",
        "Ready. Select a local media file to begin.": "Listo. Selecciona un archivo multimedia local para comenzar.",
        "Settings": "Configuración",
        "About": "Acerca de",
        "Author": "Autor",
        "Interface language": "Idioma de la interfaz",
        "Choose the language used by the application.": "Elige el idioma de la aplicación.",
        "Check for updates": "Buscar actualizaciones",
        "Check whether a newer Subway version is available.": "Comprobar si hay una versión más reciente de Subway.",
        "Current version": "Versión actual",
        "Latest version": "Última versión",
        "GitHub repository": "Repositorio de GitHub",
        "Close": "Cerrar",
        "Checking for updates…": "Buscando actualizaciones…",
        "Open the release page?": "¿Abrir la página de la versión?",
        "Update available": "Actualización disponible",
        "You are using the latest version.": "Estás usando la última versión.",
        "No published releases were found.": "No se encontraron versiones publicadas.",
        "Could not check for updates. Check your internet connection and try again.": "No se pudieron buscar actualizaciones. Comprueba tu conexión a Internet.",
        "Select a video or audio file first.": "Primero selecciona un archivo de vídeo o audio.",
        "Download the selected recognition model first.": "Primero descarga el modelo de reconocimiento seleccionado.",
        "Enter an API key first.": "Primero introduce una clave API.",
        "SRT created successfully.": "SRT creado correctamente.",
        "Translated SRT created successfully.": "SRT traducido creado correctamente.",
        "Ready": "Listo",
    },
    "uk": {
        "Local subtitle generator": "Локальний генератор субтитрів",
        "Recognition model": "Модель розпізнавання",
        "Download model": "Завантажити модель",
        "Model ready": "Модель готова",
        "1. Create subtitles": "1. Створення субтитрів",
        "No media file selected": "Медіафайл не вибрано",
        "Select video or audio": "Вибрати відео або аудіо",
        "Create SRT": "Створити SRT",
        "2. Optional translation": "2. Додатковий переклад",
        "Provider": "Провайдер",
        "Target language": "Мова перекладу",
        "Model": "Модель",
        "API key (encrypted)": "API-ключ (зашифровано)",
        "No SRT selected": "SRT-файл не вибрано",
        "Select SRT": "Вибрати SRT",
        "Translate SRT": "Перекласти SRT",
        "Status": "Стан",
        "Ready. Select a local media file to begin.": "Готово. Виберіть локальний медіафайл, щоб почати.",
        "Settings": "Налаштування",
        "About": "Про програму",
        "Author": "Автор",
        "Interface language": "Мова інтерфейсу",
        "Choose the language used by the application.": "Виберіть мову інтерфейсу програми.",
        "Check for updates": "Перевірити оновлення",
        "Check whether a newer Subway version is available.": "Перевірити, чи доступна новіша версія Subway.",
        "Current version": "Поточна версія",
        "Latest version": "Остання версія",
        "GitHub repository": "Репозиторій GitHub",
        "Close": "Закрити",
        "Checking for updates…": "Перевіряю оновлення…",
        "Open the release page?": "Відкрити сторінку релізу?",
        "Update available": "Доступне оновлення",
        "You are using the latest version.": "У вас встановлена остання версія.",
        "No published releases were found.": "Опублікованих версій поки немає.",
        "Could not check for updates. Check your internet connection and try again.": "Не вдалося перевірити оновлення. Перевірте підключення до інтернету.",
        "Select a video or audio file first.": "Спочатку виберіть відео- або аудіофайл.",
        "Download the selected recognition model first.": "Спочатку завантажте вибрану модель розпізнавання.",
        "Enter an API key first.": "Спочатку введіть API-ключ.",
        "SRT created successfully.": "SRT успішно створено.",
        "Translated SRT created successfully.": "Перекладений SRT успішно створено.",
        "Ready": "Готово",
    },
}

def translate(text: str, language: str = DEFAULT_LANGUAGE) -> str:
    code = UI_LANGUAGES.get(language, "en")
    return TEXT.get(code, {}).get(text, text)

def _settings_path() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        folder = Path(root) / "Subway"
    else:
        folder = Path.home() / ".subway"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"

def load_ui_language() -> str:
    try:
        data = json.loads(_settings_path().read_text(encoding="utf-8"))
        language = data.get("ui_language", DEFAULT_LANGUAGE)
        return language if language in UI_LANGUAGES else DEFAULT_LANGUAGE
    except (OSError, ValueError, TypeError):
        return DEFAULT_LANGUAGE

def save_ui_language(language: str) -> None:
    if language not in UI_LANGUAGES:
        language = DEFAULT_LANGUAGE
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        data = {}
    data["ui_language"] = language
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
