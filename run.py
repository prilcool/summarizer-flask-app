from tldrapp.views import app

CSRF_ENABLED = True
SECRET_KEY = 'you-will-never-guess-this'

app.config.from_object(__name__)

if __name__ == "__main__":
    app.run()