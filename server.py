from flask import Flask, request, jsonify, send_from_directory
import multiprocessing, csv, cv2, numpy as np, time, urllib.parse
from io import StringIO
from playwright.sync_api import sync_playwright
from datetime import datetime

app = Flask(__name__, static_folder='.')

# ---------- VIDEO MONITOR ----------
def is_black_frame(frame, threshold=10, ratio=0.97):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    black_pixels = np.sum(gray < threshold)
    return (black_pixels / gray.size) > ratio

def frames_are_similar(frame1, frame2, threshold=1.0):
    diff = cv2.absdiff(frame1, frame2)
    non_zero = np.count_nonzero(diff)
    percent_diff = non_zero / diff.size * 100
    return percent_diff < threshold

def monitor_single_link(name, url, duration=60):
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        return "Could not open stream"
    time.sleep(2)
    prev_frame, freeze_seconds, jitter_seconds = None, [], []
    non_black_found, consecutive_fail_count = False, 0
    for sec in range(duration):
        start = time.time()
        ret, frame = cap.read()
        if time.time() - start > 1.2:
            jitter_seconds.append(sec)
        if not ret:
            consecutive_fail_count += 1
            if consecutive_fail_count >= 5:
                break
            continue
        consecutive_fail_count = 0
        if is_black_frame(frame):
            continue
        else:
            non_black_found = True
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_frame is not None and frames_are_similar(prev_frame, gray):
            freeze_seconds.append(sec)
        prev_frame = gray
        time.sleep(1)
    cap.release()
    if not non_black_found:
        return "Blank Channel"
    if len(freeze_seconds) > 30 or consecutive_fail_count >= 5:
        return "Paused/Freeze"
    return "Smooth playback"

def monitor_stream(channel_no, name, mum_link, duration=60):
    status = monitor_single_link(name, mum_link, duration) if mum_link else "No link"
    return (channel_no, name, mum_link, status)

def run_monitor_csv(file_stream):
    file_text = StringIO(file_stream.read().decode("utf-8-sig"))
    reader = csv.DictReader(file_text)
    stream_links = [(r.get("Channel_no",""), r.get("Channel_Name",""), r.get("Channel_Link_Mumbai","")) for r in reader]
    stream_links = [x for x in stream_links if all(x)]
    if not stream_links:
        return {"error": "No channels found."}
    results = []
    for batch in range(0, len(stream_links), 5):
        with multiprocessing.Pool(len(stream_links[batch:batch+5])) as pool:
            results.extend(pool.starmap(monitor_stream, [(c[0], c[1], c[2], 60) for c in stream_links[batch:batch+5]]))
    not_working = [r for r in results if any(k in r[3] for k in ["Could not","Paused","Freeze","Blank"])]
    return {"all_results": results, "not_working_channels": not_working}

# ---------- TRENDING JIOHOTSTAR ----------
TRENDING_7D_URL = "https://www.justwatch.com/in/provider/jiohotstar?sort_by=trending_7_day"
CSV_FILE = "justwatch_hotstar_trending_2025.csv"

def scrape_jiohotstar_movies():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("[INFO] Opening JioHotstar Trending 7 Days...")
        page.goto(TRENDING_7D_URL, wait_until="load")
        page.wait_for_timeout(3000)

        seen = set()
        results = []

        last_count = 0
        scroll_attempts = 0
        while len(seen) < 100 and scroll_attempts < 50:
            cards = page.query_selector_all("div.title-list-grid__item a")
            for card in cards:
                href = card.get_attribute("href")
                if href:
                    full_link = f"https://www.justwatch.com{href}"
                    if full_link not in seen:
                        seen.add(full_link)
                        results.append(full_link)
            if len(seen) == last_count:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
            last_count = len(seen)
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1500)

        print(f"[INFO] Collected {len(results)} movie/show links.")

        final_data = []
        for link in results:
            try:
                page.goto(link, wait_until="load")
                page.wait_for_timeout(2000)

                title = "N/A"
                year = "2025"
                release_month = "2025-01"
                title_el = page.query_selector("h1")
                if title_el:
                    full_title = title_el.text_content().strip()
                    if "(" in full_title and full_title.endswith(")"):
                        title, yr = full_title.rsplit("(", 1)
                        title = title.strip()
                        yr = yr.replace(")", "").strip()
                        if yr.isdigit() and yr == "2025":
                            year = yr
                    else:
                        title = full_title

                # Release month from metadata (fallback to 2025-01)
                try:
                    meta_date = page.query_selector("span[data-testid='release-year']")
                    if meta_date:
                        release_text = meta_date.text_content().strip()  # e.g., "Feb 2025"
                        dt = datetime.strptime(release_text, "%b %Y")
                        release_month = dt.strftime("%Y-%m")
                except:
                    release_month = "2025-01"

                # Hotstar link (direct from r parameter)
                hotstar_link = ""
                provider_btns = page.query_selector_all("a[href*='hotstar.com'], a[href*='jiocinema.com']")
                for btn in provider_btns:
                    href = btn.get_attribute("href")
                    if href and "hotstar.com" in href:
                        parsed = urllib.parse.urlparse(href)
                        query = urllib.parse.parse_qs(parsed.query)
                        hotstar_link = query.get("r", [href])[0]  # decode r parameter
                        break

                # IMDb ID
                imdb_id = "N/A"
                try:
                    imdb_img = page.query_selector("img[src*='imdb']")
                    if imdb_img:
                        with context.expect_page(timeout=5000) as new_page_info:
                            imdb_img.click()
                        new_page = new_page_info.value
                        new_page.wait_for_load_state()
                        imdb_url = new_page.url
                        if "imdb.com/title/tt" in imdb_url:
                            imdb_id = imdb_url.split("/title/")[1].split("/")[0]
                        new_page.close()
                except:
                    pass

                # Trailer link
                trailer_url = "N/A"
                try:
                    trailer_button = page.query_selector("button[data-testid='play-trailer']")
                    if trailer_button:
                        trailer_button.click()
                        page.wait_for_timeout(2000)
                        iframe = page.query_selector("iframe")
                        if iframe:
                            trailer_url = iframe.get_attribute("src")
                except:
                    pass

                # Only add 2025 movies/shows
                if year == "2025":
                    final_data.append({
                        "name": title,
                        "year": year,
                        "release_month": release_month,
                        "hotstar_link": hotstar_link,
                        "imdb_id": imdb_id,
                        "trailer_link": trailer_url
                    })
                    print(f"✅ {title} ({release_month}) → {hotstar_link} → IMDb: {imdb_id}")
            except Exception as e:
                print(f"⚠️ Error for {link}: {e}")

        # Save CSV
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Movie/Show Name", "Year", "Release Month", "Hotstar Link", "IMDb ID", "Trailer Link"])
            for movie in final_data:
                writer.writerow([movie["name"], movie["year"], movie["release_month"], movie["hotstar_link"], movie["imdb_id"], movie["trailer_link"]])

        print(f"✅ Saved {len(final_data)} movies/shows to {CSV_FILE}")
        browser.close()
        return final_data

@app.route("/trending_hotstar")
def trending_hotstar():
    try:
        movies = scrape_jiohotstar_movies()
        if not movies:
            return jsonify({"error": "No movies found."}), 500
        return jsonify({"movies": movies})
    except Exception as e:
        print("❌ Error fetching trending:", e)
        return jsonify({"error": str(e)}), 500

# ---------- OTHER ROUTES ----------
@app.route("/run_monitor", methods=["POST"])
def run_monitor_route():
    if 'csv_file' not in request.files:
        return jsonify({"error": "No CSV file uploaded."})
    file = request.files['csv_file']
    return jsonify(run_monitor_csv(file))

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# ---------- MAIN ----------
if __name__ == "__main__":
    multiprocessing.freeze_support()
    app.run(debug=True)
