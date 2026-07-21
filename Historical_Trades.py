import csv 
import requests
import time
import datetime
import base64
import os
from dotenv import find_dotenv, load_dotenv
from cryptography.hazmat.primitives import hashes 
from cryptography.hazmat.primitives.asymmetric import padding 
from cryptography.hazmat.primitives.serialization import load_pem_private_key

load_dotenv(find_dotenv())

# These are the API credentials and configuration variables
API_KEY = os.getenv("API_KEY")
RSA_KEY_PATH = os.getenv("RSA_KEY_PATH", "./kalshi_private2.key") # Make sure your RSA Private is in a .key file and called here 
# if not os.path.exists(RSA_KEY_PATH):
#     raise FileNotFoundError(
#         f"Key file not found at: '{RSA_KEY_PATH}'. "
#         f"Ensure 'kalshi_private2.key' is in your project root or set correctly in .env."
#     )
TARGET_TICKER = "KXPERSONPRESMAM-45" 
OUTPUT_FILE = "kalshi_trades.csv"  
BASE_URL = "https://external-api.kalshi.com" # This will vary for the type of data you are looking for (historical or live data)


# This function is used so Kalshi can authenticate the requests for the data by using a digital signature (reads private key, creates string of request metadata, generates signature, and encodes it to Base64))
def sign_kalshi_request(private_key_path, timestamp, method, path):
    with open(private_key_path, "r", encoding="utf-8-sig") as key_file:
        key_data = key_file.read().strip().replace("\r\n", "\n") 
    private_key = load_pem_private_key(key_data.encode('utf-8'), password=None)

    str_to_sign = f"{timestamp}{method}{path}"
    signature = private_key.sign(
        str_to_sign.encode('utf-8'),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),    
            salt_length=padding.PSS.DIGEST_LENGTH  
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')


# Kalshi divides their data into different enpoints (Hierarchy system: Series---> Event---> Market) and this data has to be pulled individually then stored all together. 
def fetch_metadata_orderbook(ticker):

    master_meta = { # Dictionary to store all metadata that will be collected
        "close_time":"", 
        "status":"", 
        "volume":"", 
        "open_interest":"", 
        "event_title":"", 
        "series_ticker":"", 
        "category":"", 
        "tags":"",
        "best_yes_bid_price": "", 
        "best_yes_bid_size": "", 
        "best_yes_ask_price": "", 
        "best_yes_ask_size": ""
    }
    
    # Extraction of Market Data
    market_path = f"/trade-api/v2/markets/{ticker}"
    timestamp = str(int(datetime.datetime.now().timestamp()*1000))
    signature2 = sign_kalshi_request(RSA_KEY_PATH, timestamp, "GET", market_path) # Called signature2 so pyhton doesn't get confused with the first signature 

    # Will be used throughout this function for getting the data
    api_headers = {
        "KALSHI-ACCESS-KEY": API_KEY,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": signature2
    }

    print(f"Executing [Market Data] Extraction for: {ticker}")
    response = requests.get(f"{BASE_URL}{market_path}", headers=api_headers)
    if response.status_code == 200:
        market_data = response.json().get("market", {})
        master_meta["close_time"] = market_data.get("close_time", "")
        master_meta["status"] = market_data.get("status", "")
        master_meta["volume"] = market_data.get("volume", "")
        master_meta["open_interest"] = market_data.get("open_interest", "")
        master_meta["event_title"] = market_data.get("event_title", "")
        master_meta["series_ticker"] = market_data.get("series_ticker", "")
        event_ticker = market_data.get("event_ticker", "")
        event_data = {}

        # Extraction of Event Metadata
        if event_ticker:
            event_path = f"/trade-api/v2/events/{event_ticker}"
            signature2 = sign_kalshi_request(RSA_KEY_PATH, timestamp, "GET", event_path)
            api_headers.update({
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature2
            })
            print(f"Executing [Event Metadata] Extraction for: {event_ticker}...")
            e_res = requests.get(f"{BASE_URL}{event_path}", headers=api_headers)
            if e_res.status_code == 200:
                event_data = e_res.json().get("event", {})
                master_meta["event_title"] = event_data.get("title", "")
        
        if not master_meta["series_ticker"]:
            master_meta["series_ticker"] = event_data.get("series_ticker", "")
        
        # Extraction of Series Metadata
        if master_meta["series_ticker"]:
            series_path = f"/trade-api/v2/series/{master_meta['series_ticker']}"
            timestamp = str(int(datetime.datetime.now().timestamp()*1000))
            signature2 = sign_kalshi_request(RSA_KEY_PATH, timestamp, "GET", series_path)
            api_headers.update({
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature2
            })
            print(f"Executing [Series Metadata] Extraction for: {master_meta['series_ticker']}")
            s_res = requests.get(f"{BASE_URL}{series_path}", headers=api_headers)
            
            if s_res.status_code == 200:
                s_data = s_res.json().get("series", {})
                master_meta["category"] = s_data.get("category", "")
                t_list = s_data.get("tags", [])
                master_meta["tags"] = ", ".join(t_list) if isinstance(t_list, list) else str(t_list)
            else:
                print(f" -> Series Metadata failed ({s_res.status_code}): {s_res.text}")
    else:
        print(f" -> Market Data parent call failed ({response.status_code}): {response.text}")
    
    # Extraction of Orderbook Data (Only a snapshot, but shows liquidity depth)
    ob_path = f"/trade-api/v2/markets/{ticker}/orderbook"
    timestamp = str(int(datetime.datetime.now().timestamp()*1000))
    timestamp = str(int(datetime.datetime.now().timestamp()*1000))
    signature3 = sign_kalshi_request(RSA_KEY_PATH, timestamp, "GET", ob_path)
    api_headers.update({
    "KALSHI-ACCESS-TIMESTAMP": timestamp,
    "KALSHI-ACCESS-SIGNATURE": signature3
    })
    print(f"Executing Real-Time [Orderbook Data] Extraction for: {ticker}")
    ob_res = requests.get(f"{BASE_URL}{ob_path}", headers=api_headers)

    if ob_res.status_code == 200:
        ob_data = ob_res.json().get("orderbook_fp", {}) 
        yes_bids = ob_data.get("yes_dollars", [])
        no_bids = ob_data.get("no_dollars", [])

        if yes_bids:
            best_yes_bid = yes_bids[-1] 
            master_meta["best_yes_bid_price"] = best_yes_bid[0] # Returns dollar string (e.g., "0.4200")
            master_meta["best_yes_bid_size"] = int(float(best_yes_bid[1]))
        if no_bids:
            best_no_bid = no_bids[-1]
            # CHANGED: Reciprocal Rule (Yes Ask = $1.00 - Best No Bid)
            master_meta["best_yes_ask_price"] = str(1.0 - float(best_no_bid[0])) 
            master_meta["best_yes_ask_size"] = int(float(best_no_bid[1]))

    return master_meta # Return the collected data from the empty dictionary we made eariler 


# Function to build the CSV file with all the data we extracted in the fetch_metadata_orderbook function
def build_csv(): 
    meta_snapshot = fetch_metadata_orderbook(TARGET_TICKER) # Gets the data we extracted in the function above 

    csv_headers = [ # List of headers for the CSV file, edit this for customization of what you need for your csv file 
        "trade_id", # Indiviudal trade Log Data
        "ticker",
        "taker_side",
        "count_fp",
        "yes_price_dollars",
        "no_price_dollars",
        "created_time",
        "is_block_trade",
        "market_status", # Live Market Status 
        "total_volume",
        "open_interest",
        "close_time",
        "event_title", # Event and Series Metadata
        "series_ticker",
        "tags",
        "category", 
        "best_yes_bid_price", # Orderbook Snapshot Liquidity Data
        "best_yes_bid_size",
        "best_yes_ask_price",
        "best_yes_ask_size"
    ]

    print(f"\nConstructing Master CSV Pipeline target: {OUTPUT_FILE}")
    cursor = ""
    total_fetched = 0
    trades_path = "/trade-api/v2/historical/trades" # This would need to change if you want to get live or historical data 

    with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as file: 
        writer = csv.DictWriter(file, fieldnames=csv_headers)
        writer.writeheader()

        while True: # Repeated requests to fetch all trade data. Numbers next to varibales are just so python doesn't get confused with a varibale mentioned eariler 
            timestamp2 = str(int(datetime.datetime.now().timestamp()*1000))
            signature4 = sign_kalshi_request(RSA_KEY_PATH, timestamp2, "GET", trades_path)

            loop_headers = {
                "KALSHI-ACCESS-KEY": API_KEY,
                "KALSHI-ACCESS-TIMESTAMP": timestamp2,
                "KALSHI-ACCESS-SIGNATURE": signature4
            }
            params = {
                "ticker": TARGET_TICKER,
                "limit": 1000
            }
            if cursor:
                params["cursor"] = cursor

            response2 = requests.get(f"{BASE_URL}{trades_path}", headers=loop_headers, params=params)
            if response2.status_code != 200:
                print(f"Error fetching data: {response2.status_code}: {response2.text}")
                break

            data2 = response2.json()
            trades2 = data2.get("trades", [])
            if not trades2:
                print("No more trade logs remaining.")
                break

            for trade in trades2: # Used to combine trade specific data with the metadata from above, another area to edit if you want differnet data from the csv_headers list 
                row = {
                    # Trade Log Data 
                    "trade_id": trade.get("trade_id"),
                    "ticker": trade.get("ticker"),
                    "taker_side": trade.get("taker_side") or trade.get("side"),
                    "count_fp": trade.get("count_fp") or trade.get("count"), 
                    "yes_price_dollars": trade.get("yes_price_dollars") or trade.get("yes_price"),
                    "no_price_dollars": trade.get("no_price_dollars") or trade.get("no_price"),
                    "created_time": trade.get("created_time"),
                    "is_block_trade": trade.get("is_block_trade"),

                    # Market Data
                    "close_time": meta_snapshot["close_time"],
                    "market_status": meta_snapshot["status"],
                    "total_volume": meta_snapshot["volume"],
                    "open_interest": meta_snapshot["open_interest"],
                    
                    # Metadata from Events and Series 
                    "event_title": meta_snapshot["event_title"],
                    "series_ticker": meta_snapshot["series_ticker"],
                    "tags": meta_snapshot["tags"],
                    "category": meta_snapshot["category"],

                    # Orderbook Data, only a liquidity snapshot 
                    "best_yes_bid_price": meta_snapshot["best_yes_bid_price"],
                    "best_yes_bid_size": meta_snapshot["best_yes_bid_size"],
                    "best_yes_ask_price": meta_snapshot["best_yes_ask_price"],
                    "best_yes_ask_size": meta_snapshot["best_yes_ask_size"]
                }
                writer.writerow(row)

            total_fetched += len(trades2)
            print(f"Total Trades Fetched: {total_fetched}")
            
            cursor = data2.get("cursor") # Used to make sure the file ran properly, either cuts loop when all was downloaded correctly or if server returns an error 
            if not cursor:
                break
                
            time.sleep(0.12)

    print(f"\nFinished! All data categories successfully stitched and flattened into your CSV.")

if __name__ == "__main__":
    build_csv() 