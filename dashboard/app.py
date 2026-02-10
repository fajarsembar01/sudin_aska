from . import create_app

app = create_app()
app.config.update(
    ASKA_REPORTING_ENABLED=False,
    ASKA_REPORTING_BULLYING_ENABLED=False,
    ASKA_REPORTING_PSYCH_ENABLED=False,
    ASKA_REPORTING_CORRUPTION_ENABLED=False,
)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5002)
