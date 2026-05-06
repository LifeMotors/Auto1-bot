import requests
import json
import time
import hashlib
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os

# ============================================================
# CONFIGURATION — À REMPLIR AVANT DE LANCER
# ============================================================
AUTO1_EMAIL    = os.environ.get("AUTO1_EMAIL", "TON_EMAIL_AUTO1")
AUTO1_PASSWORD = os.environ.get("AUTO1_PASSWORD", "TON_MOT_DE_PASSE_AUTO1")
TELEGRAM_TOKEN = "8792567363:AAG3ZOoEePpb64HFSbzIyvKrbAZwDg7xQSQ"
TELEGRAM_CHAT_ID = "8776386291"
CHECK_INTERVAL = 120  # Vérification toutes les 2 minutes

# ============================================================
# CRITÈRES DE RECHERCHE
# ============================================================
CRITERES = {
    "prix_max": 3500,
    "km_max": 190000,
    "annee_min": 2006,
    "boites": ["automatique", "robotisée", "robotisee", "bmp", "auto", "dsg", "egs", "etg", "eat"],
    "modeles": [
        # PSA HDi
        "peugeot 207", "peugeot 307", "peugeot 308", "peugeot 407",
        "peugeot 508", "peugeot partner", "peugeot 3008", "peugeot 5008",
        "citroen c3", "citroen c4", "citroen c5", "citroen berlingo",
        "citroen picasso", "citroen grand picasso", "citroen c8",
        "citroen ds3", "citroen ds4", "citroen ds5",
        "ds3", "ds4", "ds5",
        "opel astra", "opel zafira", "opel meriva", "opel insignia",
        "ford focus", "ford c-max", "ford grand c-max", "ford mondeo",
        "mini one", "mini cooper",
        # Toyota
        "toyota yaris", "toyota aygo",
        "peugeot 107", "citroen c1", "citroen c2",
    ],
    "moteurs": ["1.6 hdi", "1.4 hdi", "1.6hdi", "1.4hdi", "bluehdi"],
    "pays": ["fr", "de", "be", "nl", "at", "it"],
}

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ============================================================
# ENVOI TELEGRAM
# ============================================================
def send_telegram(message: str, photo_url: str = None):
    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    try:
        if photo_url:
            r = requests.post(f"{base_url}/sendPhoto", data={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": message,
                "parse_mode": "HTML"
            }, timeout=10)
        else:
            r = requests.post(f"{base_url}/sendMessage", data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }, timeout=10)
        if r.status_code == 200:
            log.info("✅ Alerte Telegram envoyée")
        else:
            log.error(f"❌ Erreur Telegram: {r.text}")
    except Exception as e:
        log.error(f"❌ Exception Telegram: {e}")

# ============================================================
# DRIVER SELENIUM
# ============================================================
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.binary_location = "/run/current-system/sw/bin/chromium"
driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# ============================================================
# CONNEXION AUTO1
# ============================================================
def login_auto1(driver):
    log.info("🔐 Connexion à Auto1...")
    try:
        driver.get("https://www.auto1.com/fr/home")
        time.sleep(3)

        # Fermer cookie banner si présent
        try:
            cookie_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Accepter') or contains(text(), 'OK')]"))
            )
            cookie_btn.click()
            time.sleep(1)
        except:
            pass

        # Clic sur Login
        try:
            login_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'login') or contains(text(), 'Log in') or contains(text(), 'Connexion')]"))
            )
            login_link.click()
            time.sleep(2)
        except:
            driver.get("https://www.auto1.com/fr/home/login")
            time.sleep(3)

        # Remplir email
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @name='email' or @id='email']"))
        )
        email_field.clear()
        email_field.send_keys(AUTO1_EMAIL)

        # Remplir mot de passe
        pwd_field = driver.find_element(By.XPATH, "//input[@type='password']")
        pwd_field.clear()
        pwd_field.send_keys(AUTO1_PASSWORD)

        # Submit
        submit = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit.click()
        time.sleep(4)

        if "login" not in driver.current_url.lower():
            log.info("✅ Connecté à Auto1 avec succès")
            return True
        else:
            log.error("❌ Echec de connexion Auto1")
            return False

    except Exception as e:
        log.error(f"❌ Erreur login: {e}")
        return False

# ============================================================
# SCRAPING DES ANNONCES
# ============================================================
def scrape_annonces(driver):
    annonces = []
    try:
        # URL de recherche Auto1 avec filtres max
        url = "https://www.auto1.com/fr/home/buy?transmission=AUTOMATIC&priceMax=3500&mileageMax=190000&firstRegistrationMin=2006"
        driver.get(url)
        time.sleep(4)

        # Scroll pour charger les annonces
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)

        # Récupérer les cartes d'annonces
        cards = driver.find_elements(By.XPATH, "//article | //div[contains(@class, 'car-card')] | //div[contains(@class, 'vehicle-card')] | //div[contains(@class, 'listing')]")

        log.info(f"📋 {len(cards)} annonces trouvées sur la page")

        for card in cards[:50]:  # Limiter à 50 par cycle
            try:
                annonce = extraire_annonce(card)
                if annonce and correspond_aux_criteres(annonce):
                    annonces.append(annonce)
            except:
                pass

    except Exception as e:
        log.error(f"❌ Erreur scraping: {e}")

    return annonces

def extraire_annonce(card):
    annonce = {}
    try:
        # Titre / modèle
        for sel in ["h2", "h3", ".title", ".car-title", ".vehicle-title", "[class*='title']"]:
            try:
                annonce["titre"] = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except:
                pass

        # Prix
        for sel in [".price", "[class*='price']", "[data-qa*='price']"]:
            try:
                prix_text = card.find_element(By.CSS_SELECTOR, sel).text
                prix = int(''.join(filter(str.isdigit, prix_text)))
                annonce["prix"] = prix
                break
            except:
                pass

        # Kilométrage
        for sel in ["[class*='mileage']", "[class*='km']", "[data-qa*='mileage']"]:
            try:
                km_text = card.find_element(By.CSS_SELECTOR, sel).text
                km = int(''.join(filter(str.isdigit, km_text)))
                annonce["km"] = km
                break
            except:
                pass

        # Année
        for sel in ["[class*='year']", "[class*='registration']", "[data-qa*='year']"]:
            try:
                year_text = card.find_element(By.CSS_SELECTOR, sel).text
                for mot in year_text.split():
                    if mot.isdigit() and 2000 <= int(mot) <= 2030:
                        annonce["annee"] = int(mot)
                        break
            except:
                pass

        # Boîte de vitesses
        for sel in ["[class*='transmission']", "[class*='gearbox']", "[data-qa*='transmission']"]:
            try:
                annonce["boite"] = card.find_element(By.CSS_SELECTOR, sel).text.strip().lower()
                break
            except:
                pass

        # Lien
        try:
            link = card.find_element(By.TAG_NAME, "a")
            href = link.get_attribute("href")
            if href:
                annonce["lien"] = href if href.startswith("http") else f"https://www.auto1.com{href}"
        except:
            pass

        # Photo
        try:
            img = card.find_element(By.TAG_NAME, "img")
            annonce["photo"] = img.get_attribute("src")
        except:
            pass

        # ID unique
        annonce["id"] = hashlib.md5((annonce.get("titre", "") + str(annonce.get("prix", "")) + str(annonce.get("km", ""))).encode()).hexdigest()

        return annonce if annonce.get("titre") else None

    except:
        return None

# ============================================================
# VÉRIFICATION DES CRITÈRES
# ============================================================
def correspond_aux_criteres(annonce):
    titre = annonce.get("titre", "").lower()
    boite = annonce.get("boite", "").lower()
    prix = annonce.get("prix", 9999999)
    km = annonce.get("km", 9999999)
    annee = annonce.get("annee", 0)

    # Prix
    if prix and prix > CRITERES["prix_max"]:
        return False

    # Kilométrage
    if km and km > CRITERES["km_max"]:
        return False

    # Année
    if annee and annee < CRITERES["annee_min"]:
        return False

    # Boîte automatique/robotisée
    boite_ok = any(b in boite or b in titre for b in CRITERES["boites"])
    if not boite_ok:
        return False

    # Modèle ET moteur (logique spéciale)
    # Pour Toyota Yaris/Aygo/107/C1/C2 : pas besoin de moteur HDi
    toyotas = ["toyota yaris", "toyota aygo", "peugeot 107", "citroen c1", "citroen c2"]
    est_toyota = any(m in titre for m in toyotas)

    if est_toyota:
        return True

    # Pour PSA : vérifier modèle + moteur HDi
    modele_ok = any(m in titre for m in CRITERES["modeles"])
    moteur_ok = any(m in titre for m in CRITERES["moteurs"])

    return modele_ok and moteur_ok

# ============================================================
# FORMATAGE ALERTE
# ============================================================
def formater_alerte(annonce):
    titre = annonce.get("titre", "Véhicule")
    prix = annonce.get("prix", "?")
    km = annonce.get("km", "?")
    annee = annonce.get("annee", "?")
    boite = annonce.get("boite", "?")
    lien = annonce.get("lien", "https://www.auto1.com")

    msg = f"""🚨 <b>NOUVELLE ANNONCE DÉTECTÉE !</b>

🚗 <b>{titre}</b>

💰 Prix : <b>{prix:,} €</b>
📅 Année : <b>{annee}</b>
🛣️ Kilométrage : <b>{km:,} km</b>
⚙️ Boîte : <b>{boite}</b>

🔗 <a href="{lien}">Voir l'annonce sur Auto1</a>

⏰ {datetime.now().strftime("%d/%m/%Y à %H:%M")}"""

    return msg

# ============================================================
# BOUCLE PRINCIPALE
# ============================================================
def main():
    log.info("🤖 Démarrage du bot Auto1...")
    send_telegram("🤖 <b>Bot Auto1 démarré !</b>\n\nJe surveille les annonces selon tes critères et je t'alerte dès qu'une opportunité apparaît. 🚗")

    annonces_vues = set()
    driver = None

    while True:
        try:
            log.info(f"🔍 Nouvelle vérification — {datetime.now().strftime('%H:%M:%S')}")

            if driver is None:
                driver = get_driver()
                if not login_auto1(driver):
                    log.error("Impossible de se connecter, nouvelle tentative dans 5 min")
                    driver.quit()
                    driver = None
                    time.sleep(300)
                    continue

            annonces = scrape_annonces(driver)
            nouvelles = [a for a in annonces if a.get("id") not in annonces_vues]

            if nouvelles:
                log.info(f"🎯 {len(nouvelles)} nouvelle(s) annonce(s) trouvée(s) !")
                for annonce in nouvelles:
                    msg = formater_alerte(annonce)
                    photo = annonce.get("photo")
                    send_telegram(msg, photo)
                    annonces_vues.add(annonce["id"])
                    time.sleep(2)
            else:
                log.info("😴 Aucune nouvelle annonce pour le moment")

        except Exception as e:
            log.error(f"❌ Erreur principale: {e}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                driver = None

        log.info(f"⏳ Prochaine vérification dans {CHECK_INTERVAL//60} minutes")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
