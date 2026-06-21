"""
Парсер объявлений о недвижимости с Avito
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import random
import csv
import re
import os
from urllib.parse import urljoin

# ---------- НАСТРОЙКИ ----------

BASE_URL = "https://www.avito.ru"
LISTING_PAGE_URL = BASE_URL + "/moskva/kvartiry/prodam?p={page}" #укажите то, что вы хотите парсить
MAX_PAGES = 2
DELAY_RANGE = (5, 8)

# ⚠️ ВАЖНО: Введите свои данные
AVITO_LOGIN = "укажите свой телефон/почту"
AVITO_PASSWORD = "укажите свой пароль"

OUTPUT_TXT = "avito_listings.txt"
OUTPUT_CSV = "avito_listings.csv"


# ---------- ИНИЦИАЛИЗАЦИЯ БРАУЗЕРА ----------

def init_driver():
    options = webdriver.ChromeOptions()
    
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    })
    
    return driver


# ---------- АВТОРИЗАЦИЯ С ПОДДЕРЖКОЙ СМС ----------

def login_to_avito(driver):
    print("\n🔐 Авторизуюсь на Avito...")
    
    try:
        driver.get("https://www.avito.ru")
        time.sleep(3)
        
        try:
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Войти')]"))
            )
            login_btn.click()
        except:
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-marker="header/login-button"]'))
            )
            login_btn.click()
        print("  ✅ Нажал кнопку 'Войти'")
        time.sleep(2)
        
        phone_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//input[@name='login']"))
        )
        phone_input.clear()
        time.sleep(0.5)
        for char in AVITO_LOGIN:
            phone_input.send_keys(char)
            time.sleep(0.1)
        print(f"  ✅ Введен телефон: {AVITO_LOGIN}")
        time.sleep(1)
        
        try:
            continue_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Продолжить')]")
        except:
            continue_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        continue_btn.click()
        print("  ✅ Нажал 'Продолжить'")
        time.sleep(3)
        
        password_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//input[@name='password']"))
        )
        password_input.clear()
        time.sleep(0.5)
        for char in AVITO_PASSWORD:
            password_input.send_keys(char)
            time.sleep(0.1)
        print("  ✅ Введен пароль")
        time.sleep(1)
        
        try:
            login_submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Войти')]")
        except:
            login_submit = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        login_submit.click()
        print("  ✅ Нажал 'Войти'")
        time.sleep(3)
        
        print("\n  ⏳ Проверяю, нужен ли СМС-код...")
        
        sms_attempts = 0
        while sms_attempts < 3:
            try:
                sms_input = driver.find_element(By.XPATH, "//input[@placeholder='Код из СМС']")
                if sms_input:
                    print("\n  📱 Требуется СМС-код!")
                    print("  Введите код из СМС вручную в открывшемся окне браузера")
                    print("  ⏳ Ожидаю ввода кода...")
                    
                    WebDriverWait(driver, 120).until(
                        EC.invisibility_of_element_located((By.XPATH, "//input[@placeholder='Код из СМС']"))
                    )
                    print("  ✅ СМС-код введен!")
                    time.sleep(3)
                    break
            except:
                break
            sms_attempts += 1
            time.sleep(2)
        
        print("\nВы прошли авторизацию? (y/n): ")
        answer = input().strip().lower()
        return answer == 'y'
            
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return False


# ---------- СБОР ССЫЛОК ----------

def get_listing_links(driver, page_num):
    url = LISTING_PAGE_URL.format(page=page_num)
    print(f"Загружаю страницу списка: {url}")
    
    driver.get(url)
    time.sleep(2)
    
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-marker="item-title"]'))
        )
    except:
        print("  Не удалось загрузить объявления")
        return []
    
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
    
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")
    
    links = []
    selectors = [
        '[data-marker="item-title"]',
        '.iva-item-titleLink',
        '.item-description-title-link'
    ]
    
    for selector in selectors:
        elements = soup.select(selector)
        if elements:
            for elem in elements:
                href = elem.get("href")
                if href:
                    full_url = urljoin(BASE_URL, href)
                    if full_url not in links:
                        links.append(full_url)
            break
    
    print(f"  Найдено объявлений: {len(links)}")
    return links


# ---------- ПОЛУЧЕНИЕ ТЕЛЕФОНА ----------

def get_phone_number(driver):
    phone = None
    
    try:
        try:
            phone_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-marker="item-phone-button"]'))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", phone_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", phone_btn)
            time.sleep(3)
            
            phone_elem = driver.find_element(By.CSS_SELECTOR, '[data-marker="item-phone"]')
            if phone_elem:
                phone = phone_elem.text.strip()
                if phone:
                    print(f"    📞 Телефон (кнопка): {phone}")
                    return phone
        except:
            pass
        
        try:
            phone_elem = driver.find_element(By.CSS_SELECTOR, '[data-marker="item-phone"]')
            if phone_elem:
                phone = phone_elem.text.strip()
                if phone:
                    print(f"    📞 Телефон (открыт): {phone}")
                    return phone
        except:
            pass
        
        try:
            tel_link = driver.find_element(By.CSS_SELECTOR, 'a[href^="tel:"]')
            if tel_link:
                phone = tel_link.get_attribute('href').replace('tel:', '').strip()
                if phone:
                    print(f"    📞 Телефон (tel:): {phone}")
                    return phone
        except:
            pass
        
        try:
            scripts = driver.find_elements(By.TAG_NAME, "script")
            for script in scripts:
                script_text = script.get_attribute("innerHTML")
                if script_text and '"phone"' in script_text:
                    match = re.search(r'"phone":"([^"]+)"', script_text)
                    if match:
                        phone = match.group(1)
                        if phone and len(phone) >= 10:
                            print(f"    📞 Телефон (JSON): {phone}")
                            return phone
        except:
            pass
        
        page_text = driver.page_source
        patterns = [
            r'\+7\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}',
            r'8\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}',
            r'\d{3}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}'
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text)
            if match:
                phone = match.group(0)
                phone = re.sub(r'[^\d+]', '', phone)
                if len(phone) >= 10:
                    print(f"    📞 Телефон (текст): {phone}")
                    return phone
    except Exception as e:
        print(f"    Ошибка при получении телефона: {e}")
    
    if phone:
        phone = re.sub(r'\s+', ' ', phone).strip()
        if phone.startswith('8') and len(phone) == 11:
            phone = '+7' + phone[1:]
    
    return phone


# ---------- ПАРСИНГ ОБЪЯВЛЕНИЯ ----------

def parse_listing(driver, url):
    print(f"\n  Парсю: {url[:100]}...")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            driver.get(url)
            time.sleep(3)
            
            page_text = driver.page_source.lower()
            if "captcha" in page_text or "проверка" in page_text or "доступ" in page_text:
                print("  ⚠️ Обнаружена капча или блокировка, пробую обновить...")
                driver.refresh()
                time.sleep(5)
                continue
            
            try:
                WebDriverWait(driver, 20).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'h1')),
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-marker="item-title"]')),
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'span[itemprop="price"]')),
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-marker="item-price"]'))
                    )
                )
                break
            except:
                print(f"  Попытка {attempt+1}: не удалось загрузить страницу")
                if attempt == max_retries - 1:
                    return None
                continue
                
        except Exception as e:
            print(f"  Ошибка при загрузке: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(3)
    
    for _ in range(2):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
    
    phone = get_phone_number(driver)
    
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")
    
    def safe_text(selector):
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else None
    
    def get_by_marker(marker):
        el = soup.select_one(f'[data-marker="{marker}"]')
        return el.get_text(strip=True) if el else None
    
    title = get_by_marker("item-title") or safe_text("h1")
    if not title:
        title = safe_text('[itemprop="name"]') or "Неизвестно"
    
    price = get_by_marker("item-price")
    if not price:
        price = safe_text('span[itemprop="price"]')
    if not price:
        price = safe_text('[data-marker="item-price"]')
    
    address = get_by_marker("item-address")
    if not address:
        address = safe_text('span[itemprop="address"]')
    if not address:
        address = safe_text('[class*="address"]')
    
    area_m2 = None
    rooms = None
    floor = None
    
    params_container = soup.select_one('[data-marker="item-view/item-params"]')
    if not params_container:
        params_container = soup.select_one('[class*="item-params"]')
    if not params_container:
        params_container = soup.select_one('[class*="params"]')
    
    if params_container:
        items = params_container.select('li, div[class*="param"], p')
        for item in items:
            text = item.get_text(strip=True)
            text_lower = text.lower()
            
            if 'м²' in text_lower or 'м2' in text_lower:
                area_match = re.search(r'(\d+[\s,.]*\d*)\s*м[²2]', text)
                if area_match:
                    area_m2 = area_match.group(1).replace(',', '.').replace(' ', '')
            elif 'комн' in text_lower:
                rooms_match = re.search(r'(\d+)\s*комн', text)
                if rooms_match:
                    rooms = rooms_match.group(1)
            elif 'этаж' in text_lower:
                floor_match = re.search(r'(\d+)\s*(?:из\s*)?(\d+)?', text_lower)
                if floor_match:
                    if floor_match.group(2):
                        floor = f"{floor_match.group(1)} из {floor_match.group(2)}"
                    else:
                        floor = floor_match.group(1)
    
    if not area_m2 or not rooms:
        page_text = soup.get_text()
        
        if not area_m2:
            area_match = re.search(r'(\d+[\s,.]*\d*)\s*м[²2]', page_text)
            if area_match:
                area_m2 = area_match.group(1).replace(',', '.').replace(' ', '')
        
        if not rooms:
            rooms_match = re.search(r'(\d+)\s*комн', page_text)
            if rooms_match:
                rooms = rooms_match.group(1)
        
        if not floor:
            floor_match = re.search(r'(\d+)\s*(?:из\s*)?(\d+)?\s*этаж', page_text)
            if floor_match:
                if floor_match.group(2):
                    floor = f"{floor_match.group(1)} из {floor_match.group(2)}"
                else:
                    floor = floor_match.group(1)
    
    publish_date = get_by_marker("item-date")
    if not publish_date:
        publish_date = safe_text('span[data-marker="item-date"]')
    if not publish_date:
        publish_date = safe_text('[class*="date"]')
    
    description = get_by_marker("item-description")
    if not description:
        description = safe_text('div[data-marker="item-description"]')
    if not description:
        description = safe_text('[class*="description"]')
    
    data = {
        "url": url,
        "title": title,
        "price": price,
        "address": address,
        "area_m2": area_m2,
        "rooms": rooms,
        "floor": floor,
        "publish_date": publish_date,
        "description": description,
        "seller_phone": phone,
    }
    
    return data


# ---------- ПОСТЕПЕННОЕ СОХРАНЕНИЕ ----------

def append_to_txt(item, filename=OUTPUT_TXT):
    with open(filename, "a", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        for key, value in item.items():
            f.write(f"{key}: {value}\n")
        f.write("\n")


def append_to_csv(item, filename=OUTPUT_CSV):
    file_exists = os.path.isfile(filename)
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=item.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(item)


def append_to_files(item):
    append_to_txt(item)
    append_to_csv(item)


# ---------- ОСНОВНОЙ ЦИКЛ ----------

def main():
    driver = init_driver()
    
    try:
        if not login_to_avito(driver):
            print("\n⚠️ Не удалось авторизоваться.")
            choice = input("Продолжить без авторизации? (y/n): ")
            if choice.lower() != 'y':
                driver.quit()
                return
        
        all_listing_links = []
        
        for page in range(1, MAX_PAGES + 1):
            links = get_listing_links(driver, page)
            all_listing_links.extend(links)
            time.sleep(random.uniform(DELAY_RANGE[0], DELAY_RANGE[1]))
        
        all_listing_links = list(dict.fromkeys(all_listing_links))
        print(f"\n📌 Всего уникальных ссылок: {len(all_listing_links)}\n")
        
        results = []
        for i, link in enumerate(all_listing_links, 1):
            print(f"\n[{i}/{len(all_listing_links)}]")
            
            try:
                item = parse_listing(driver, link)
                if item:
                    results.append(item)
                    append_to_files(item)
                    print(f"    💾 Сохранено в файлы")
                    print(f"    🏠 {item['title']}")
                    print(f"    💰 {item['price']}")
                    if item['area_m2']:
                        print(f"    📐 {item['area_m2']} м²")
                    if item['seller_phone']:
                        print(f"    ✅ ТЕЛЕФОН: {item['seller_phone']}")
                    else:
                        print(f"    ⚠️ Телефон не найден")
                
                time.sleep(random.uniform(DELAY_RANGE[0], DELAY_RANGE[1]))
                
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                continue
        
        if results:
            phones_found = sum(1 for r in results if r['seller_phone'])
            print(f"\n✅ Готово! Сохранено {len(results)} объявлений")
            print(f"📞 С телефонами: {phones_found} ({phones_found/len(results)*100:.1f}%)")
            
            if phones_found > 0:
                print("\n📞 Найденные телефоны:")
                for r in results:
                    if r['seller_phone']:
                        print(f"  - {r['title'][:50]}... → {r['seller_phone']}")
        else:
            print("\n❌ Не удалось спарсить ни одного объявления.")
            
    finally:
        driver.quit()


if __name__ == "__main__":
    main()


#by krest1c_