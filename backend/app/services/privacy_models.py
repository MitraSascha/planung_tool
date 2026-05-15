from app.core.settings import settings


def load_privacy_models() -> dict[str, bool | str]:
    status: dict[str, bool | str] = {
        "gliner_model_name": settings.gliner_model_name,
        "presidio_loaded": False,
        "gliner_loaded": False,
    }

    try:
        from presidio_analyzer import AnalyzerEngine

        AnalyzerEngine()
        status["presidio_loaded"] = True
    except Exception as exc:
        status["presidio_error"] = str(exc)

    try:
        from gliner import GLiNER

        GLiNER.from_pretrained(settings.gliner_model_name)
        status["gliner_loaded"] = True
    except Exception as exc:
        status["gliner_error"] = str(exc)

    return status


if __name__ == "__main__":
    print(load_privacy_models())
