from flask import Flask
from google_recaptcha import ReCaptcha

app = Flask(__name__)
recaptcha = ReCaptcha(
    app=app, site_key="6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT"
)


print(recaptcha.verify())
