from flask import Flask, request, jsonify
from flask_cors import CORS
from paddleocr import PaddleOCR
import os
import pandas as pd
import time
from symspellpy import SymSpell, Verbosity
from geopy.geocoders import Nominatim
from flask import send_file
from waitress import serve  # Use Waitress for production


app = Flask(__name__)
CORS(app)  # Enable CORS for frontend access
ocr = PaddleOCR(use_angle_cls=True)  # Initialize PaddleOCR

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Ensure upload folder exists

# Load dictionary
sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
sym_spell.load_dictionary("words.txt", term_index=0, count_index=1)

def correct_text(text):
    """Correct OCR text using SymSpell."""
    words = text.split()  # Split into words
    corrected_words = []

    for word in words:
        suggestions = sym_spell.lookup(word, Verbosity.CLOSEST, max_edit_distance=2)
        corrected_words.append(suggestions[0].term if suggestions else word)

    return " ".join(corrected_words)

def parse_address(text):
    """Extract structured address components."""
    geolocator = Nominatim(user_agent="my_address_parser")
    try:
        location = geolocator.geocode(text, addressdetails=True)
        if location and 'address' in location.raw:
            address = location.raw['address']
            return {
                "text": text, 
                "street": address.get("road", ""),
                "city": address.get("city", address.get("town", address.get("village", ""))),
                "state": address.get("state", ""),
                "country": address.get("country", ""),
                "postal_code": address.get("postcode", ""),
                "latitude": location.latitude,
                "longitude": location.longitude
            }
        else:
            return {
                "text": text, 
                "street": "N/A",
                "city": "N/A",
                "state": "N/A",
                "country": "N/A",
                "postal_code": "N/A",
                "latitude": "N/A",
                "longitude": "N/A"
            }
    except Exception:
        return {"error": "Unable to parse address"}

def save_to_excel(data, image_path):
    """Save extracted address and image path to an Excel file."""
    excel_filename = "output.xlsx"
    df_new = pd.DataFrame([{
        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "Extracted Text": data["text"],
        "Street": data.get("street", ""),
        "City": data.get("city", ""),
        "State": data.get("state", ""),
        "Country": data.get("country", ""),
        "Postal Code": data.get("postal_code", ""),
        "Latitude": data.get("latitude", ""),
        "Longitude": data.get("longitude", ""),
        "Image Path": image_path
    }])

    if os.path.exists(excel_filename):
        df_existing = pd.read_excel(excel_filename)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        df_combined.to_excel(excel_filename, index=False)
    else:
        df_new.to_excel(excel_filename, index=False)

@app.route("/upload", methods=["POST"])
def upload_file():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    unique_filename = f"image_{time.strftime('%Y%m%d_%H%M%S')}.png"
    image_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    image.save(image_path)

    # Perform OCR
    result = ocr.ocr(image_path, cls=True)
    extracted_text = "\n".join([word[1][0] for line in result for word in line])

    if not extracted_text.strip():
        return jsonify({"error": "No text extracted from image"}), 400

    # Correct OCR mistakes
    corrected_text = correct_text(extracted_text)

    # Parse the address
    parsed_address = parse_address(corrected_text)

    # Save results to Excel
    save_to_excel(parsed_address, image_path)

    return jsonify(parsed_address)


@app.route("/download", methods=["GET"])
def download_excel():
    """Allow users to download the latest Excel file."""
    excel_filename = "output.xlsx"

    if not os.path.exists(excel_filename):
        return jsonify({"error": "No records found"}), 404

    return send_file(excel_filename, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    serve(app, host="0.0.0.0", port=port)
