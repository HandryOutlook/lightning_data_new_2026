import json
import requests
import re

def clean_json_text(raw_text):
    """
    Removes trailing commas before closing brackets and braces 
    to fix malformed JSON strings.
    """
    return re.sub(r',\s*([\]}])', r'\1', raw_text)

def scrape_lightning_data(base_url, output_file="lightning_data_2026_summer.json"):
    try:
        all_new_strikes = []
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.metoffice.gov.uk/"
        }
        
        # 1. FETCH BASE URL
        try:
            response = requests.get(base_url, headers=headers)
            response.raise_for_status()
            
            # Sanitize the raw text before parsing
            sanitized_text = clean_json_text(response.text)
            json_data = json.loads(sanitized_text) 
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from base URL {base_url}: {str(e)}")
            return
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Met Office API sent malformed base JSON data: {str(e)}")
            print("Raw response snippet:", response.text[:500])
            # Dump the full raw response so we can inspect exactly what broke,
            # instead of just a 500-char snippet that may not include the error location.
            try:
                with open("debug_bad_base_response.txt", "w", encoding="utf-8") as dbg:
                    dbg.write(response.text)
                print("Full raw response saved to debug_bad_base_response.txt for inspection")
            except Exception as dbg_e:
                print(f"Could not save debug dump: {dbg_e}")
            return
        except KeyError as e:
            print(f"Data format error in response from base URL: {str(e)}")
            return

        # Extract initial strikes
        base_strikes = json_data.get("lightning_strikes", [])
        all_new_strikes.extend(base_strikes)
        print(f"Successfully fetched {len(base_strikes)} strikes from base URL")

        # Extract chunks and generate chunk URLs
        chunks = json_data.get("chunks", [])
        chunk_urls = [f"{base_url}?chunk={chunk['chunk']}" for chunk in chunks]
        if not chunks:
            print("No chunks found in base URL response.")

        # 2. PROCESS PAGINATED CHUNKS
        for url in chunk_urls:
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                
                # Sanitize the raw text before parsing
                sanitized_text = clean_json_text(response.text)
                json_data = json.loads(sanitized_text)
                
                new_strikes = json_data.get("lightning_strikes", [])
                all_new_strikes.extend(new_strikes)
                print(f"Successfully fetched {len(new_strikes)} strikes from {url}")
                
            except requests.exceptions.RequestException as e:
                print(f"Error fetching data from {url}: {str(e)}")
                continue
            except (json.JSONDecodeError, ValueError) as e: 
                print(f"JSON Parsing Error on chunk {url}: {str(e)} - Skipping bad API payload.")
                # Dump the full raw response for this chunk so we can inspect
                # exactly what the API sent, rather than guessing after the fact.
                try:
                    chunk_label = url.split("chunk=")[-1] if "chunk=" in url else "unknown"
                    debug_filename = f"debug_bad_chunk_{chunk_label}.txt"
                    with open(debug_filename, "w", encoding="utf-8") as dbg:
                        dbg.write(response.text)
                    print(f"Full raw response saved to {debug_filename} for inspection")
                except Exception as dbg_e:
                    print(f"Could not save debug dump for {url}: {dbg_e}")
                continue
            except KeyError as e:
                print(f"Data format error in response from {url}: {str(e)}")
                continue
        
        if not all_new_strikes:
            print("No new strikes fetched from any URL.")
            return
        
        # 3. LOAD OR INITIALIZE LOCAL FILE
        try:
            with open(output_file, 'r') as f:
                existing_data = json.load(f)
        except (FileNotFoundError, ValueError): 
            existing_data = {
                "lightning_strikes": [],
                "total_strikes": 0
            }
        
        existing_strikes = existing_data.get("lightning_strikes", [])
        
        # Optimized O(1) deduplication
        seen_strikes = set()
        for s in existing_strikes:
            coords = s.get("coordinates", [0, 0])
            seen_strikes.add((s.get("strike_time"), coords[1], coords[0]))
        
        unique_new_strikes = []
        for new_strike in all_new_strikes:
            coords = new_strike.get("coordinates", [0, 0])
            strike_key = (new_strike.get("strike_time"), coords[1], coords[0])
            
            if strike_key not in seen_strikes:
                seen_strikes.add(strike_key)
                unique_new_strikes.append(new_strike)
        
        updated_strikes = existing_strikes + unique_new_strikes
        total_strikes = len(updated_strikes)
        
        print(f"\nTotal number of strikes to commit: {total_strikes}")
        
        # 4. WRITE OUT CLEAN DATASET
        data_to_save = {
            "lightning_strikes": updated_strikes,
            "total_strikes": total_strikes
        }
        
        with open(output_file, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        print(f"Data successfully updated in {output_file}")
        
    except Exception as e:
        print(f"Unexpected top-level error occurred: {str(e)}")

base_url = "https://data.consumer-digital.api.metoffice.gov.uk/v1/lightning"

if __name__ == "__main__":
    scrape_lightning_data(base_url)
