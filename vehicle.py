# app.py (Web-based + SaaS-ready)

import os
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import openai
from threading import Thread

# Load env variables
load_dotenv()

WP_API_URL = os.getenv("WP_API_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

app = Flask(__name__)

def scrape_respectmotors(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    data = {
        "title": soup.find("h1").text.strip() if soup.find("h1") else "Untitled",
        "make": None,
        "model": None,
        "year": None,
        "mileage": None,
        "fuel_type": None,
        "grade": None,
        "images": []
    }
    
    for img_tag in soup.find_all("img"):
        img_url = img_tag.get("src")
        if img_url and "vehicles" in img_url:
            data["images"].append(img_url)
    return data

def scrape_autoaccess(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    data = {
        "title": soup.find("h1").text.strip() if soup.find("h1") else "Untitled",
        "make": None,
        "model": None,
        "year": None,
        "mileage": None,
        "fuel_type": None,
        "grade": None,
        "images": []
    }

    for row in soup.select(".table-responsive table tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            label = cells[0].text.lower()
            value = cells[1].text.strip()
            if "make" in label:
                data["make"] = value
            elif "model" in label:
                data["model"] = value
            elif "year" in label:
                data["year"] = value
            elif "mileage" in label:
                data["mileage"] = value
            elif "fuel" in label:
                data["fuel_type"] = value
            elif "grade" in label:
                data["grade"] = value

    for img_tag in soup.find_all("img"):
        img_url = img_tag.get("src")
        if img_url and "vehicle" in img_url:
            data["images"].append(img_url)
    return data

def generate_description(data):
    prompt = f"""
    Write a professional vehicle listing description:
    Make: {data['make']}
    Model: {data['model']}
    Year: {data['year']}
    Mileage: {data['mileage']}
    Fuel Type: {data['fuel_type']}
    Auction Grade: {data['grade']}
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a vehicle listing assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message['content'].strip()

def estimate_price(data):
    price = 3000
    if data['grade'] == '4': price += 500
    if data['fuel_type'] == 'Diesel': price += 300
    return price

def upload_images(images):
    media_ids = []
    for url in images:
        img_data = requests.get(url).content
        filename = url.split("/")[-1]
        r = requests.post(
            WP_API_URL.replace("/posts", "/media"),
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
            },
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            files={'file': (filename, img_data)}
        )
        if r.status_code == 201:
            media_ids.append(r.json().get("id"))
    return media_ids

def post_to_wordpress(title, content, media_ids):
    featured_id = media_ids[0] if media_ids else None
    post_data = {
        "title": title,
        "content": content + "\n\nDisclaimer: Auto-generated content.",
        "status": "publish",
        "featured_media": featured_id,
    }
    r = requests.post(WP_API_URL, json=post_data, auth=(WP_USERNAME, WP_APP_PASSWORD))
    return r.json()

def process_url_async(url):
    if "respectmotors" in url:
        data = scrape_respectmotors(url)
    elif "autoaccess" in url:
        data = scrape_autoaccess(url)
    else:
        return {"error": "Unsupported auction site"}

    data['description'] = generate_description(data)
    data['price'] = estimate_price(data)
    media_ids = upload_images(data['images'])
    result = post_to_wordpress(data['title'], data['description'], media_ids)
    return result

@app.route("/generate", methods=["POST"])
def generate():
    urls = request.json.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    results = []
    for url in urls:
        thread = Thread(target=lambda u: results.append(process_url_async(u)), args=(url,))
        thread.start()
        thread.join()

    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
