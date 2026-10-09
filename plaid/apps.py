import os, json
from datetime import date

from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from extractors.matching import matches_any
from extractors.plaid_ext import PlaidExtractor, fetch_and_store
from paths import get_records_dir

load_dotenv()
app = Flask(__name__)

plaid_engine = PlaidExtractor(os.getenv("PLAID_CLIENT_ID"), os.getenv("PLAID_SECRET"), os.getenv("PLAID_ENV"))

_INDEX_HTML = None
_index_path = os.path.join(os.path.dirname(__file__), "index.html")
if os.path.exists(_index_path):
    with open(_index_path, encoding="utf-8") as f:
        _INDEX_HTML = f.read()

# --- Helper Functions ---

TOKENS_FILE = "tokens.json"
ITEMS_FILE = "items.json"

def _load_json(filename):
    path = os.path.join(get_records_dir(), filename)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def _save_json(filename, data):
    os.makedirs(get_records_dir(), exist_ok=True)
    path = os.path.join(get_records_dir(), filename)
    with open(path, "w") as f:
        json.dump(data, f)

def load_tokens():
    return _load_json(TOKENS_FILE)

def load_item_metadata():
    return _load_json(ITEMS_FILE)

def save_token(item_id, access_token):
    tokens = load_tokens()
    tokens[item_id] = access_token
    _save_json(TOKENS_FILE, tokens)

def save_item_metadata(item_id, institution_id, institution_name):
    items = load_item_metadata()
    items[item_id] = {
        "item_id": item_id,
        "institution_id": institution_id,
        "institution_name": institution_name,
    }
    _save_json(ITEMS_FILE, items)

# --- The Core Method Call Class ---

class DataExporter:
    @staticmethod
    def run_export(start_date=None, end_date=None, output_dir=None, bank_filter=None, account_filter=None):
        """
        The central method to pull data.
        bank_filter: list of strings (e.g., ['Chase']) or a single string.
        """
        tokens = load_tokens()
        metadata = load_item_metadata()
        output_dir = output_dir or get_records_dir()
        end_date = end_date or date.today()
        start_date = start_date or date(2000, 1, 1)

        selected_item_ids = []
        if bank_filter:
            selected_item_ids = [
                item_id
                for item_id in tokens
                if matches_any(
                    bank_filter,
                    metadata.get(item_id, {}).get("institution_name", ""),
                    metadata.get(item_id, {}).get("institution_id", ""),
                    item_id,
                )
            ]
        else:
            selected_item_ids = list(tokens.keys())

        results = []
        for item_id in selected_item_ids:
            file_path = fetch_and_store(
                plaid_engine.client,
                tokens[item_id],
                item_id=item_id,
                start_date=start_date,
                end_date=end_date,
                output_dir=output_dir,
                account_filter=account_filter
            )
            results.append({"item_id": item_id, "file": file_path})
        return results

# --- Flask Routes ---

@app.route('/')
def index():
    if _INDEX_HTML is None:
        return "Plaid connect page missing.", 404
    return render_template_string(_INDEX_HTML)


@app.route('/api/create_link_token', methods=['POST'])
def link_token():
    req = LinkTokenCreateRequest(
        products=[Products('transactions')],
        client_name="Data Aggregator",
        country_codes=[CountryCode('US')],
        language='en',
        user=LinkTokenCreateRequestUser(client_user_id='user_1')
    )
    return jsonify(plaid_engine.client.link_token_create(req).to_dict())

@app.route('/api/exchange_public_token', methods=['POST'])
def exchange():
    pub_token = request.json.get('public_token')
    exchange_resp = plaid_engine.client.item_public_token_exchange(ItemPublicTokenExchangeRequest(public_token=pub_token))
    access_token, item_id = exchange_resp['access_token'], exchange_resp["item_id"]
    
    # Resolve Metadata
    inst_id = plaid_engine.client.item_get(ItemGetRequest(access_token=access_token)).to_dict()['item']['institution_id']
    inst_name = plaid_engine.client.institutions_get_by_id(InstitutionsGetByIdRequest(
        institution_id=inst_id, country_codes=[CountryCode("US")]
    )).to_dict()['institution']['name']

    save_token(item_id, access_token)
    save_item_metadata(item_id, inst_id, inst_name)
    
    # Use method call for initial pull
    DataExporter.run_export(bank_filter=item_id)
    return jsonify({"status": "connected", "item_id": item_id})

if __name__ == "__main__":
    app.run(port=5000)
