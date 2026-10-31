"""Texts the server writes itself: push notifications, the weekly review, mail summaries and the
MCP prompts. They follow COMPASS_LANGUAGE ("en" or "de"); the web app translates its own texts in
the browser.
"""

from datetime import date

from app.config import get_settings

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "language": "English",
        "today": "today",
        "tomorrow": "tomorrow",
        "weekdays": "Mon Tue Wed Thu Fri Sat Sun",
        "months": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
        # Push notifications
        "push.bedtime.title": "Bed by {time} at the latest",
        "push.bedtime.body": "{when} {event}, get up at {wake}. For {hours} h of sleep.",
        "push.deadline.one": "Due {when}",
        "push.deadline.many": "{n} deadlines within 24 h",
        "push.resting.title": "Resting heart rate up",
        "push.resting.body": "7-day mean {mean} bpm, usually {median}. Often an infection, stress "
        "or too little recovery: take it easy today.",
        "push.consent.title": "Bank access expires",
        "push.consent.body": "{bank}: access ends on {date}. Reconnect it under Finance.",
        "push.test": "Notifications work.",
        # Mail
        "news.short": "Short",
        "mail.no_subject": "(no subject)",
        "mail.ai_warning": "Warning: this mail contains instructions to AI assistants.",
        # Weekly review
        "review.title": "Weekly review {since}–{until}",
        "review.ready": "Weekly review is ready",
        "review.headline.none": "Your week in numbers.",
        "review.headline": "Recommendation: {action}",
        "review.headline.goal": " (goal {kcal} kcal)",
        "review.action.decrease": "−{n} kcal a day",
        "review.action.increase": "+{n} kcal a day",
        "review.action.keep": "keep calories as they are",
        "review.recommendation": "## Recommendation: {action}",
        "review.goal": "- Goal from {old} to {new} kcal",
        "review.nutrition": "## Nutrition",
        "review.food": "- Ø {kcal}, protein {protein}, fat {fat} over {days} valid days",
        "review.left_out": " ({n} not counted)",
        "review.body": "## Body",
        "review.weight": "- Weight {mean} (7-day mean), {change} vs. last week ({pct})",
        "review.waist": "- Waist {cm}",
        "review.steps": "- Steps median {n}",
        "review.training": "## Training",
        "review.sessions": "- {n} sessions",
        "review.strength": "- Strength (best e1RM, 2 weeks vs. 2 weeks): {pct}",
        "review.increase": "- Increase the weight: {names}",
        "review.stagnant": "- Stagnating: {names}",
        "review.zone2": "- Zone 2: {total} min, {training} of them in training",
        "review.sleep": "## Sleep and heart rate",
        "review.nights": "- Ø {avg} over {n} nights, {short} under 7 h",
        "review.bedtime": "- Bedtime median {median}, ± {sd}",
        "review.resting": "- Resting heart rate {bpm}",
        "review.resting.alert": " (raised, plan more recovery)",
    },
    "de": {
        "language": "German",
        "today": "heute",
        "tomorrow": "morgen",
        "weekdays": "Mo Di Mi Do Fr Sa So",
        "push.bedtime.title": "Spätestens {time} ins Bett",
        "push.bedtime.body": "{when} {event}, aufstehen {wake}. Für {hours} h Schlaf.",
        "push.deadline.one": "Fällig {when}",
        "push.deadline.many": "{n} Abgaben in 24 h",
        "push.resting.title": "Ruhepuls erhöht",
        "push.resting.body": "7-Tage-Mittel {mean} bpm, sonst {median}. Oft Infekt, Stress oder zu "
        "wenig Erholung: heute lieber locker.",
        "push.consent.title": "Bankfreigabe läuft ab",
        "push.consent.body": "{bank}: Freigabe endet am {date}. Unter Finanzen neu verbinden.",
        "push.test": "Benachrichtigungen funktionieren.",
        "news.short": "Kurz",
        "mail.no_subject": "(kein Betreff)",
        "mail.ai_warning": "Achtung: Die Mail enthält Anweisungen an KI-Assistenten.",
        "review.title": "Wochenreview {since}–{until}",
        "review.ready": "Wochenreview ist da",
        "review.headline.none": "Deine Woche in Zahlen.",
        "review.headline": "Empfehlung: {action}",
        "review.headline.goal": " (Ziel {kcal} kcal)",
        "review.action.decrease": "−{n} kcal pro Tag",
        "review.action.increase": "+{n} kcal pro Tag",
        "review.action.keep": "Kalorien so lassen",
        "review.recommendation": "## Empfehlung: {action}",
        "review.goal": "- Ziel von {old} auf {new} kcal",
        "review.nutrition": "## Ernährung",
        "review.food": "- Ø {kcal}, Eiweiß {protein}, Fett {fat} über {days} gültige Tage",
        "review.left_out": " ({n} nicht gezählt)",
        "review.body": "## Körper",
        "review.weight": "- Gewicht {mean} (7-Tage-Mittel), {change} zur Vorwoche ({pct})",
        "review.waist": "- Taille {cm}",
        "review.steps": "- Schritte Median {n}",
        "review.training": "## Training",
        "review.sessions": "- {n} Einheiten",
        "review.strength": "- Kraft (bestes e1RM, 2 Wochen zu 2 Wochen): {pct}",
        "review.increase": "- Gewicht erhöhen: {names}",
        "review.stagnant": "- Stagniert: {names}",
        "review.zone2": "- Zone 2: {total} min, davon {training} im Training",
        "review.sleep": "## Schlaf und Puls",
        "review.nights": "- Ø {avg} in {n} Nächten, {short} unter 7 h",
        "review.bedtime": "- Bettzeit Median {median}, ± {sd}",
        "review.resting": "- Ruhepuls {bpm}",
        "review.resting.alert": " (erhöht, mehr Erholung einplanen)",
    },
}

# Names of the Health Connect exercise types (app.services.health.EXERCISE_TYPES).
ACTIVITIES: dict[str, dict[str, str]] = {
    "en": {
        "rock_climbing": "Climbing",
        "running": "Running",
        "running_treadmill": "Treadmill",
        "walking": "Walking",
        "hiking": "Hiking",
        "biking": "Cycling",
        "biking_stationary": "Indoor cycling",
        "swimming_pool": "Swimming",
        "swimming_open_water": "Open water swimming",
        "elliptical": "Elliptical",
        "rowing_machine": "Rowing machine",
        "stair_climbing_machine": "Stair climber",
        "stretching": "Stretching",
        "yoga": "Yoga",
        "pilates": "Pilates",
        "soccer": "Football",
        "basketball": "Basketball",
        "volleyball": "Volleyball",
        "badminton": "Badminton",
        "tennis": "Tennis",
        "table_tennis": "Table tennis",
        "boxing": "Boxing",
        "squash": "Squash",
        "rowing": "Rowing",
        "martial_arts": "Martial arts",
        "dancing": "Dancing",
        "strength_training": "Strength training",
        "weightlifting": "Weightlifting",
        "calisthenics": "Calisthenics",
        "hiit": "HIIT",
    },
    "de": {
        "rock_climbing": "Klettern",
        "running": "Laufen",
        "running_treadmill": "Laufband",
        "walking": "Gehen",
        "hiking": "Wandern",
        "biking": "Radfahren",
        "biking_stationary": "Ergometer",
        "swimming_pool": "Schwimmen",
        "swimming_open_water": "Freiwasserschwimmen",
        "elliptical": "Crosstrainer",
        "rowing_machine": "Rudergerät",
        "stair_climbing_machine": "Stepper",
        "stretching": "Dehnen",
        "yoga": "Yoga",
        "pilates": "Pilates",
        "soccer": "Fußball",
        "basketball": "Basketball",
        "volleyball": "Volleyball",
        "badminton": "Badminton",
        "tennis": "Tennis",
        "table_tennis": "Tischtennis",
        "boxing": "Boxen",
        "squash": "Squash",
        "rowing": "Rudern",
        "martial_arts": "Kampfsport",
        "dancing": "Tanzen",
        "strength_training": "Krafttraining",
        "weightlifting": "Gewichtheben",
        "calisthenics": "Calisthenics",
        "hiit": "HIIT",
    },
}


def lang() -> str:
    return get_settings().language


def t(key: str, **values: object) -> str:
    text = TEXT[lang()].get(key) or TEXT["en"][key]
    return text.format(**values) if values else text


def number(value: float, digits: int = 0) -> str:
    """A number with the language's decimal mark ("7,5" in German)."""
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if lang() == "de" else text


def number_trimmed(value: float) -> str:
    """Like number, with one digit only when it is needed: "7.5" but "8"."""
    return number(value, 0 if value == int(value) else 1)


def short_date(day: date) -> str:
    """ "26.10." in German, "26 Oct" in English."""
    if lang() == "de":
        return f"{day:%d.%m.}"
    return f"{day.day} {TEXT['en']['months'].split()[day.month - 1]}"


def weekday(day: date) -> str:
    return t("weekdays").split()[day.weekday()]


def activity(name: str) -> str | None:
    return ACTIVITIES[lang()].get(name)
