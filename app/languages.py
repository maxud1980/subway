"""Language names and codes used for recognition and translation."""

LANGUAGES = {
    'Afrikaans': 'af', 'Akan': 'ak', 'Albanian': 'sq', 'Amharic': 'am',
    'Arabic': 'ar', 'Armenian': 'hy', 'Azerbaijani': 'az', 'Basque': 'eu',
    'Belarusian': 'be', 'Bengali': 'bn', 'Bulgarian': 'bg', 'Burmese (Myanmar)': 'my',
    'Catalan': 'ca', 'Chinese (Simplified)': 'zh-Hans', 'Chinese (Traditional)': 'zh-Hant',
    'Croatian': 'hr', 'Czech': 'cs', 'Danish': 'da', 'Dutch': 'nl',
    'English': 'en', 'Estonian': 'et', 'Filipino': 'fil', 'Finnish': 'fi',
    'French': 'fr', 'Galician': 'gl', 'Georgian': 'ka', 'German': 'de',
    'Greek': 'el', 'Gujarati': 'gu', 'Hausa': 'ha', 'Hebrew': 'he',
    'Hindi': 'hi', 'Hungarian': 'hu', 'Icelandic': 'is', 'Indonesian': 'id',
    'Italian': 'it', 'Japanese': 'ja', 'Javanese': 'jv', 'Kannada': 'kn',
    'Kazakh': 'kk', 'Khmer': 'km', 'Kinyarwanda': 'rw', 'Korean': 'ko',
    'Lao': 'lo', 'Latvian': 'lv', 'Lithuanian': 'lt', 'Macedonian': 'mk',
    'Malay': 'ms', 'Malayalam': 'ml', 'Maltese': 'mt', 'Marathi': 'mr', 'Mongolian': 'mn',
    'Nepali': 'ne', 'Norwegian': 'no', 'Persian': 'fa', 'Polish': 'pl',
    'Portuguese (Brazil)': 'pt-BR', 'Portuguese (Portugal)': 'pt-PT', 'Punjabi': 'pa',
    'Romanian': 'ro', 'Russian': 'ru', 'Serbian': 'sr', 'Sindhi': 'sd',
    'Sinhala': 'si', 'Slovak': 'sk', 'Slovenian': 'sl', 'Spanish': 'es',
    'Sundanese': 'su', 'Swahili': 'sw', 'Swedish': 'sv', 'Tamil': 'ta',
    'Telugu': 'te', 'Thai': 'th', 'Turkish': 'tr', 'Ukrainian': 'uk',
    'Urdu': 'ur', 'Uzbek': 'uz', 'Vietnamese': 'vi', 'Zulu': 'zu',
}


def language_code(name: str) -> str:
    return LANGUAGES.get(name, name.lower().replace(" ", "-")[:12] or "xx")


# Codes that name the same language differently ("nb-NO" is Norwegian Bokmål, listed as "no").
_ALIASES = {"nb": "no", "nn": "no", "iw": "he", "in": "id", "tl": "fil"}


def base_language(code: str) -> str:
    """'uk-UA' → 'uk', 'zh-Hans' → 'zh', 'nb-NO' → 'no': the part that names the language."""
    base = code.split("-")[0].lower()
    return _ALIASES.get(base, base)


def language_name(code: str) -> str:
    for name, value in LANGUAGES.items():
        if value.lower() == code.lower():
            return name
    return code


def names_for(codes) -> list[str]:
    """Language names for base codes: 'pt' gives both Portuguese variants."""
    bases = {base_language(code) for code in codes}
    return sorted(name for name, code in LANGUAGES.items() if base_language(code) in bases)
