import json
import requests
from datetime import datetime

def scrape_lightning_data(base_url, output_file="lightning_data_2026_summer.json"):
    try:
        all_new_strikes = []
        
        # Fetch the base URL to get chunks and strikes
        try:
            response = requests.get(base_url)
            response.raise_for_status()  
            json_data = response.json()  
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Error fetching/parsing data from base URL {base_url}: {str(e)}")
            return
        except KeyError as e:
            print(f"Data format error in response from base URL: {str(e)}")
            return

        # Extract strikes from base URL
        base_strikes = json_data.get("lightning_strikes", [])
        all_new_strikes.extend(base_strikes)
        print(f"Successfully fetched {len(base_strikes)} strikes from base URL {base_url}")

        # Extract chunks and generate chunk URLs
        chunks = json_data.get("chunks", [])
        chunk_urls = [f"{base_url}?chunk={chunk['chunk']}" for chunk in chunks]
        if not chunks:
            print("No chunks found in base URL response.")

        # Process each chunk URL
        for url in chunk_urls:
            try:
                response = requests.get(url)
                response.raise_for_status()  
                json_data = response.json()  # This throws json.JSONDecodeError if malformed
                
                # Extract strikes from chunk data
                new_strikes = json_data.get("lightning_strikes", [])
                all_new_strikes.extend(new_strikes)
                print(f"Successfully fetched {len(new_strikes)} strikes from {url}")
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                print(f"Error fetching/parsing data from {url}: {str(e)}")
                continue  # Skip this chunk and move to the next one instead of crashing!
            except KeyError as e:
                print(f"Data format error in response from {url}: {str(e)}")
                continue
        
        if not all_new_strikes:
            print("No new strikes fetched from any URL.")
            return
        
        # Load existing data if file exists
        try:
            with open(output_file, 'r') as f:
                existing_data = json.load(f)
        except FileNotFoundError:
            existing_data = {"lightning_strikes": [], "total_strikes": 0}
        except json.JSONDecodeError as e:
            print(f"Warning: Local file {output_file} is corrupted ({str(e)}). Starting fresh.")
            existing_data = {"lightning_strikes": [], "total_strikes": 0}
        
        # Extract existing strikes
        existing_strikes = existing_data.get("lightning_strikes", [])
        
        # Check for new unique strikes (based on strike_time and coordinates)
        unique_new_strikes = []
        existing_set = {(s["strike_time"], tuple(s["coordinates"])) for s in existing_strikes}
        
        for new_strike in all_new_strikes:
            strike_key = (new_strike["strike_time"], tuple(new_strike["coordinates"]))
            if strike_key not in existing_set:
                unique_new_strikes.append(new_strike)
                existing_set.add(strike_key) # Prevent duplicates within the new batch itself
        
        # Combine strikes
        updated_strikes = existing_strikes + unique_new_strikes
        total_strikes = len(updated_strikes)
        
        # Print the results
        print("\nNew Lightning Strikes Added:")
        if unique_new_strikes:
            # Only print first few to keep GitHub Actions logs clean if there are thousands
            for strike in unique_new_strikes[:10]:
                strike_time = strike["strike_time"]
                coords = strike["coordinates"]
                print(f"Time: {strike_time} | Coordinates: Lat {coords[1]}, Lon {coords[0]}")
            if len(unique_new_strikes) > 10:
                print(f"... and {len(unique_new_strikes) - 10} more strikes.")
        else:
            print("No new strikes to add.")
        
        print(f"\nTotal number of strikes in file: {total_strikes}")
        
        # Prepare updated data to save
        data_to_save = {
            "lightning_strikes": updated_strikes,
            "total_strikes": total_strikes
        }
        
        # Save to JSON file
        with open(output_file, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        print(f"\nData updated in {output_file}")
        
    except Exception as e:
        print(f"Unexpected error occurred: {str(e)}")

# Base URL
base_url = "https://data.consumer-digital.api.metoffice.gov.uk/v1/lightning"

# Call the function
scrape_lightning_data(base_url)
