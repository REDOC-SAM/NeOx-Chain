import os
import time
import json
import hashlib
import sqlite3
import ast
from web3 import Web3
from dotenv import load_dotenv
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

neoxt_url = "https://eth-sepolia.g.alchemy.com/v2/liUJMW3QYmgUdrJJqGCrDG0BB54LfCs7"
web3 = Web3(Web3.HTTPProvider(neoxt_url))

if web3.is_connected():
    print("Connected to blockchain")
else:
    print("Failed to connect to blockchain")

from_address = "0xaB1c6305753434A2aC08B7BdF3f2a68266B869fe"
private_key = "918f459a07d1d70f409fcd5419d682131ddde97f1c46ad4c62c9aff00a155ce9"
chain_id = 11155111

app = Flask(__name__)
dictionary = {}

# SQLite setup
conn = sqlite3.connect('document_verification.db')
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_name TEXT,
    document_hash TEXT UNIQUE,
    txn_hash TEXT,
    timestamp TEXT
)''')
conn.commit()
conn.close()

# Function to store data in DB
def store_in_db(participant_name, document_hash, txn_hash):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('document_verification.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO documents (participant_name, document_hash, txn_hash, timestamp)
        VALUES (?, ?, ?, ?)''',
        (participant_name, document_hash, txn_hash, timestamp)
    )
    conn.commit()
    conn.close()

# Verification based on document_hash
def verify_data(json_data: dict[str, str]) -> str:
    json_string = json.dumps(json_data, sort_keys=True)
    calculated_hash = hashlib.sha256(json_string.encode()).hexdigest()

    conn = sqlite3.connect('document_verification.db')
    c = conn.cursor()
    c.execute(
        'SELECT document_hash FROM documents WHERE document_hash = ?', 
        (calculated_hash,)
    )
    result = c.fetchone()
    conn.close()

    if result:
        return "✅ Verification successful! Data is authentic."
    else:
        return "❌ Verification failed! Data doesn't exist or has been altered."

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/verify')
def verify():
    return render_template('verify.html')

@app.route('/upload_details')
def upload_details():
    return render_template('upload.html')

# Unique upload route clearly defined
@app.route('/upload', methods=['POST'])
def upload():
    global dictionary   
    if 'image' not in request.files:
        return "No file part", 400
    image = request.files['image']
    if image.filename == '':
        return "No selected file", 400

    if not os.path.exists("uploads"):
        os.makedirs("uploads")
    save = os.path.join('uploads', image.filename)
    image.save(save)

    sample_file = genai.upload_file(path=save, display_name="PASS IMAGE")
    file = genai.get_file(name=sample_file.name)

    model = genai.GenerativeModel("gemini-1.5-flash")
    result = model.generate_content(
        [file, "\n\n", "Extract the text content from this image. Organise the text into paragraph format, and extract the name, hackathon name from the text. respond with json containing the text, hackathon_name and name extracted."],
    )

    try:
        result_data = ast.literal_eval(result.text)
    except Exception as e:
        print("Parsing error:", e)
        result_data = {"text": "", "hackathon_name": "", "name": ""}

    dictionary = {
        "hackathon_name": result_data.get("hackathon_name", ""),
        "name": result_data.get("name", "")
    }

    verify_result = verify_data(dictionary)

    return render_template('result.html', dictionary=dictionary, verify_result=verify_result)

# New clear and separate route to store/upload data to DB & blockchain
@app.route('/upload_data', methods=['POST'])
def upload_data():
    if 'image' not in request.files:
        return "No file part", 400
    image = request.files['image']
    if image.filename == '':
        return "No selected file", 400
    if not os.path.exists("uploads"):
        os.makedirs("uploads")
    save = os.path.join('uploads', image.filename)
    image.save(save)

    sample_file = genai.upload_file(path=save, display_name="PASS IMAGE")
    file = genai.get_file(name=sample_file.name)

    model = genai.GenerativeModel("gemini-1.5-flash")
    result = model.generate_content(
        [file, "\n\n", "Extract the text content from this image. Organise the text into paragraph format, and extract the name, hackathon name from the text. respond with json containing the text, hackathon_name and name extracted."],
    )

    try:
        result_data = ast.literal_eval(result.text)
    except Exception as e:
        print("Parsing error:", e)
        result_data = {"text": "", "hackathon_name": "", "name": ""}

    data = {
        "hackathon_name": result_data.get("hackathon_name", ""),
        "name": result_data.get("name", "")
    }

    data_string = json.dumps(data, sort_keys=True)
    data_hash = hashlib.sha256(data_string.encode()).hexdigest()
    
    account = web3.eth.account.from_key(private_key)
    nonce = web3.eth.get_transaction_count(account.address)

    transaction = {
        'to': "0x0000000000000000000000000000000000000000",
        'value': 0,
        'gas': 2000000,
        'gasPrice': web3.to_wei('50', 'gwei'),
        'nonce': nonce,
        'chainId': chain_id,
        'data': web3.to_bytes(hexstr=data_hash)
    }

    signed_txn = web3.eth.account.sign_transaction(transaction, private_key)
    txn_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)

    store_in_db(data["name"], data_hash, web3.to_hex(txn_hash))

    return jsonify({"transaction_hash": web3.to_hex(txn_hash)})

@app.route('/result')
def result():
    global dictionary
    verify_result = verify_data(dictionary)
    return render_template('result.html', dictionary=dictionary, verify_result=verify_result)

if __name__ == '__main__':
    app.run(debug=True)
