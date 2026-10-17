"use strict";
// Địa chỉ email nhận báo cáo nội dung AI (BẮT BUỘC điền trước khi đăng store)
const REPORT_EMAIL = "";
const CATEGORY = {code:"Lập trình",math:"Toán",translate:"Dịch",long:"Văn bản dài",quick:"Hỏi nhanh",general:"Chung",manual:"Chọn tay"};
const SAMPLES = ["Viết hàm Python kiểm tra số nguyên tố","Dịch sang tiếng Anh: Hôm nay trời đẹp, đi dạo thôi","Gợi ý cách lên kế hoạch học tiếng Anh trong 3 tháng"];
const $ = s => document.querySelector(s);
const store = {
  get(k, d){ try{ const v = JSON.parse(localStorage.getItem(k)); return v === null ? d : v; }catch{ return d; } },
  set(k, v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch{} }
};

let deviceId = store.get("deviceId", null);
if(!deviceId){
  deviceId = (crypto.randomUUID ? crypto.randomUUID() : Date.now() + Math.random().toString(36).slice(2)).replace(/[^A-Za-z0-9_-]/g, "-");
  store.set("deviceId", deviceId);
}
let history = store.get("history", []);
let busy = false;
const save = () => store.set("history", history.slice(-100));

function el(tag, cls, text){ const e = document.createElement(tag); if(cls) e.className = cls; if(text !== undefined) e.textContent = text; return e; }

function render(){
  const box = $("#chat");
  box.replaceChildren();
  if(!history.length){
    const e = el("div", "empty");
    e.append(el("h1", "", "Hỏi gì cũng được"), el("p", "", "Xiaoli AI tự chọn model phù hợp nhất cho từng câu hỏi. Thử một câu:"));
    SAMPLES.forEach(s => { const b = el("button", "", s); b.type = "button"; b.onclick = () => send(s); e.append(b); });
    box.append(e);
    return;
  }
  history.forEach((m, i) => {
    const d = el("div", "msg " + m.role);
    if(m.role === "user"){ d.textContent = m.text; }
    else {
      if(m.label) d.append(el("span", "route", `${CATEGORY[m.category] || "Chung"} → ${m.label}`));
      const t = el("div", "text" + (m.pending ? " pending" : ""), m.text); d.append(t);
      if(m.note) d.append(el("div", "note", m.note));
      if(m.error) d.append(el("div", "err", m.error));
      if(!m.pending && m.text){
        const a = el("div", "acts");
        [["up", "Hữu ích"], ["down", "Chưa tốt"]].forEach(([v, name]) => {
          const b = el("button", "", name); b.type = "button"; b.setAttribute("aria-pressed", m.fb === v);
          b.onclick = () => { m.fb = m.fb === v ? null : v; save(); render(); };
          a.append(b);
        });
        const r = el("button", "", "Báo cáo"); r.type = "button"; r.onclick = () => report(m); a.append(r);
        d.append(a);
      }
    }
    box.append(d);
  });
  box.scrollTop = box.scrollHeight;
}

function report(m){
  if(!REPORT_EMAIL){ alert("Chưa cấu hình email nhận báo cáo."); return; }
  const body = `Model: ${m.label || ""}\n\nNội dung bị báo cáo:\n${m.text}`;
  location.href = `mailto:${REPORT_EMAIL}?subject=${encodeURIComponent("Báo cáo nội dung Xiaoli AI")}&body=${encodeURIComponent(body)}`;
}

function onEvent(ev, msg){
  if(ev.type === "meta"){ msg.label = ev.label; msg.category = ev.category; }
  else if(ev.type === "chunk"){ msg.text += ev.text; }
  else if(ev.type === "blocked" || ev.type === "error"){ msg.error = ev.message; }
  else if(ev.type === "done" && ev.truncated){ msg.note = "Câu trả lời đã bị cắt vì quá dài."; }
}

async function send(prompt){
  if(busy || !prompt.trim()) return;
  busy = true; $("#send").disabled = true;
  history.push({role: "user", text: prompt});
  const msg = {role: "ai", text: "", pending: true};
  history.push(msg); render();
  try{
    const res = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Device-Id": deviceId},
      body: JSON.stringify({prompt, model: $("#model").value || undefined})
    });
    const rem = res.headers.get("X-RateLimit-Remaining");
    if(rem !== null) $("#quota").textContent = `Còn ${rem} lượt hôm nay.`;
    if(!res.ok){
      const j = await res.json().catch(() => ({}));
      throw new Error(typeof j.detail === "string" ? j.detail : `Không gửi được (lỗi ${res.status}). Hãy thử lại.`);
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for(;;){
      const {done, value} = await reader.read();
      if(done) break;
      buf += dec.decode(value, {stream: true});
      let i;
      while((i = buf.indexOf("\n\n")) >= 0){
        const block = buf.slice(0, i); buf = buf.slice(i + 2);
        if(block.startsWith("data: ")){ try{ onEvent(JSON.parse(block.slice(6)), msg); }catch{} }
      }
      render();
    }
  }catch(e){
    msg.error = e instanceof TypeError ? "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại." : e.message;
  }finally{
    msg.pending = false; busy = false; $("#send").disabled = false; save(); render();
  }
}

async function loadModels(){
  try{
    const j = await (await fetch("/models")).json();
    j.models.forEach(m => { const o = el("option", "", m.label); o.value = m.id; $("#model").append(o); });
  }catch{}
}

$("#form").addEventListener("submit", e => { e.preventDefault(); const p = $("#prompt").value; $("#prompt").value = ""; $("#prompt").style.height = "auto"; send(p); });
$("#prompt").addEventListener("keydown", e => { if(e.key === "Enter" && !e.shiftKey){ e.preventDefault(); $("#form").requestSubmit(); } });
$("#prompt").addEventListener("input", e => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; });
$("#clear").addEventListener("click", () => { if(confirm("Xóa toàn bộ lịch sử chat trên máy này?")){ history = []; save(); render(); } });
history.forEach(m => { m.pending = false; });
render(); loadModels();
if("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
