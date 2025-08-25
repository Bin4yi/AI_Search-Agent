from dotenv import load_dotenv
import os
import requests
from urllib.parse import quote_plus
from snapshot_operations import download_snapshot, poll_snapshot_status

load_dotenv()  # Fixed: Added missing parentheses
dataset_id = "gd_lvz8ah06191smkebj4"

def _make_api_request(url, **kwargs):
    api_key = os.getenv("BRIGHTDATA_API_KEY")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, **kwargs)
        
        # Better error logging
        if not response.ok:
            print(f"API request failed: {response.status_code} - {response.text}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return None
    except Exception as e:
        print(f"Unknown error: {e}")
        return None
    
def serp_search(query: str, engine: str = "google"):
    if engine == "google":
        base_url = "https://www.google.com/search"
    elif engine == "bing":
        base_url = "https://www.bing.com/search"
    else:
        raise ValueError("Unsupported search engine. Use 'google' or 'bing'.")

    url = "https://api.brightdata.com/request"

    # Try multiple zone configurations
    zones_to_try = ["ai_agent"]
    
    for zone in zones_to_try:
        payload = {
            "zone": zone,
            "url": f"{base_url}?q={quote_plus(query)}&brd_json=1",
            "format": "raw"
        }
        
        print(f"Trying {engine} search with zone: {zone}")
        full_response = _make_api_request(url, json=payload)
        
        if full_response:
            extracted_data = {
                "knowledge": full_response.get("knowledge", {}),
                "organic": full_response.get("organic", []),
            }
            print(f"✅ {engine} search successful with zone: {zone}")
            return extracted_data
        else:
            print(f"❌ {engine} search failed with zone: {zone}")
    
    print(f"❌ All zones failed for {engine} search")
    return None


def _trigger_and_download_snapshot(trigger_url, params, data, operation_name="operation"):
    print(f"🔄 Triggering {operation_name} snapshot...")
    trigger_result = _make_api_request(trigger_url, params=params, json=data)
    if not trigger_result:
        print(f"❌ Failed to trigger {operation_name} snapshot")
        return None

    snapshot_id = trigger_result.get("snapshot_id")
    if not snapshot_id:
        print(f"❌ No snapshot_id returned for {operation_name}")
        return None

    print(f"⏳ Polling snapshot {snapshot_id} for {operation_name}...")
    if not poll_snapshot_status(snapshot_id):
        print(f"❌ Snapshot {snapshot_id} failed or timed out")
        return None

    print(f"📥 Downloading snapshot {snapshot_id} for {operation_name}...")
    raw_data = download_snapshot(snapshot_id)
    return raw_data


def reddit_search_api(keyword, date="All time", sort_by="Hot", num_of_posts=75):
    trigger_url = "https://api.brightdata.com/datasets/v3/trigger"

    params = {
        "dataset_id": "gd_lvz8ah06191smkebj4",
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword"
    }

    data = [
        {
            "keyword": keyword,
            "date": date,
            "sort_by": sort_by,
            "num_of_posts": num_of_posts,
        }
    ]

    raw_data = _trigger_and_download_snapshot(
        trigger_url, params, data, operation_name="reddit"
    )

    if not raw_data:
        print("❌ No data returned from Reddit search")
        return None

    print(f"Debug: Raw data type: {type(raw_data)}")
    print(f"Debug: Raw data sample: {raw_data[:2] if isinstance(raw_data, list) and len(raw_data) > 0 else raw_data}")

    parsed_data = []
    for i, post in enumerate(raw_data):
        try:
            if isinstance(post, dict):
                parsed_post = {
                    "title": post.get("title", ""),
                    "url": post.get("url", "")
                }
            elif isinstance(post, str):
                parsed_post = {
                    "title": post,
                    "url": ""
                }
            else:
                print(f"Warning: Unexpected post type {type(post)}, skipping")
                continue
                
            parsed_data.append(parsed_post)
        except Exception as e:
            print(f"Error processing post {i}: {e}")
            continue

    print(f"✅ Parsed {len(parsed_data)} Reddit posts")
    return {"parsed_posts": parsed_data, "total_found": len(parsed_data)}


def reddit_post_retrieval(urls, days_back=10, load_all_replies=False, comment_limit=""):
    if not urls:
        print("❌ No URLs provided for Reddit post retrieval")
        return None

    trigger_url = "https://api.brightdata.com/datasets/v3/trigger"

    params = {
        "dataset_id": "gd_lvzdpsdlw09j6t702",
        "include_errors": "true"
    }

    data = [
        {
            "url": url,
            "days_back": days_back,
            "load_all_replies": load_all_replies,
            "comment_limit": comment_limit
        }
        for url in urls
    ]

    raw_data = _trigger_and_download_snapshot(
        trigger_url, params, data, operation_name="reddit comments"
    )
    if not raw_data:
        print("❌ No comments data returned")
        return None

    parsed_comments = []
    for comment in raw_data:
        parsed_comment = {
            "comment_id": comment.get("comment_id"),
            "content": comment.get("comment"),
            "date": comment.get("date_posted"),
        }
        parsed_comments.append(parsed_comment)

    print(f"✅ Parsed {len(parsed_comments)} Reddit comments")
    return {"comments": parsed_comments, "total_retrieved": len(parsed_comments)}
