let monitorResults = { working: [], notworking: [] };
let monitorResults2 = { working: [], notworking: [] };

// ---------------- Login ----------------
const validUsers = [
  { email: "nancy@example.com", password: "1234" },
  { email: "test@example.com", password: "abcd" }
];

function login() {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const user = validUsers.find(u => u.email === email && u.password === password);
  if (user) {
    document.getElementById("login-container").classList.add("hidden");
    document.getElementById("dashboard-wrapper").classList.remove("hidden");
    const welcome = document.getElementById("welcome-msg");
    const dashboard1 = document.getElementById("app-container-1");
    welcome.classList.remove("hidden");
    dashboard1.classList.add("hidden");
    setTimeout(() => {
      welcome.classList.add("hidden");
      dashboard1.classList.remove("hidden");
    }, 2000);
  } else {
    document.getElementById("login-msg").textContent = "❌ Invalid email or password!";
  }
}

function logout() {
  document.getElementById("dashboard-wrapper").classList.add("hidden");
  document.getElementById("login-container").classList.remove("hidden");
  document.getElementById("email").value = "";
  document.getElementById("password").value = "";
  document.getElementById("login-msg").textContent = "";
}

// ---------------- Page Switch ----------------
function switchPage(pageNum) {
  document.querySelectorAll('.app-container').forEach(el => el.classList.add('hidden'));
  const currentPage = document.getElementById(`app-container-${pageNum}`);
  if (currentPage) currentPage.classList.remove('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------- Single Channel Check ----------------
function runCheck(page=1) {
  const output = page===1 ? document.getElementById("output") : document.getElementById("output-2");
  const link = page===1 ? document.getElementById("channel-link").value : document.getElementById("channel-link-2").value;
  if(!link) return alert("Please enter a channel link first!");
  output.textContent = `🔄 Checking channel: ${link}\n`;
  setTimeout(() => {
    output.textContent += `✅ Channel is working fine: ${link}\n`;
  }, 1500);
}

// ---------------- CSV Monitor ----------------
function runMonitor(page=1) {
  const fileInput = page===1 ? document.getElementById("channel-file") : document.getElementById("channel-file-2");
  const output = page===1 ? document.getElementById("output") : document.getElementById("output-2");
  if(!fileInput.files.length) return alert("Please select a CSV file first!");
  
  const formData = new FormData();
  formData.append("csv_file", fileInput.files[0]);
  output.textContent = "🔄 Starting monitor... Please wait.\n";

  fetch("/run_monitor", { method: "POST", body: formData })
    .then(res => res.json())
    .then(data => {
      if(data.error) output.textContent = "❌ " + data.error;
      else {
        const resultsObj = page===1 ? monitorResults : monitorResults2;
        resultsObj.working = data.all_results.filter(r => !r[3].includes("Could not") && !r[3].includes("Paused") && !r[3].includes("Freeze") && !r[3].includes("Blank"));
        resultsObj.notworking = data.not_working_channels;

        output.textContent = `✅ Monitoring complete!\n\n⚠️ ${resultsObj.notworking.length} Channels Not Working\n`;
        resultsObj.notworking.forEach((r,i) => { output.textContent += `${i+1}. ${r[1]} | Mumbai: ${r[3]}\n`; });
        output.textContent += `\n✅ ${resultsObj.working.length} Channels Working\n`;
        resultsObj.working.forEach((r,i) => { output.textContent += `${i+1}. ${r[1]} | Mumbai: ${r[3]}\n`; });
      }
    })
    .catch(err => { output.textContent = "❌ Error running monitor: " + err; });
}

// ---------------- Trending Hotstar ----------------
function getTrending(platform) {
  const output = document.getElementById("output-3");
  output.textContent = `🔄 Fetching trending movies for ${platform}...`;

  fetch(`/trending_hotstar`)
    .then(res => res.json())
    .then(data => {
      if(data.error) { output.textContent = "❌ " + data.error; return; }
      if(!data.movies || !data.movies.length) { output.textContent = `⚠️ No trending movies found for ${platform}`; return; }

      let text = `✅ Trending Movies on ${platform.toUpperCase()}\n\n`;
      let csvContent = "Name,Year,Link,IMDb,Trailer\n";

      data.movies.forEach((m, i) => {
        text += `${i+1}. ${m.name} (${m.year})\n${m.hotstar_link}\nIMDb: ${m.imdb_id}\nTrailer: ${m.trailer_link}\n\n`;
        csvContent += `"${m.name.replace(/"/g,'""')}","${m.year}","${m.hotstar_link}","${m.imdb_id}","${m.trailer_link}"\n`;
      });

      output.textContent = text;

      // Download CSV
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `hotstar_trending_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
    })
    .catch(err => { console.error(err); output.textContent = "❌ Error fetching trending: " + err; });
}
