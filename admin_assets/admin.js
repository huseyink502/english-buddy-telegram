/* Untrusted message text uses textContent, never innerHTML. */
(() => {
  const chat = document.getElementById('chat');
  if (!chat) return;
  const container = document.getElementById('messages');
  const status = document.getElementById('chat-status');
  const older = document.getElementById('older');
  let busy = false, before = 0, revision = null;
  const records = new Map();
  function render() {
    container.replaceChildren();
    [...records.values()].sort((a,b) => a.message_id-b.message_id).forEach(msg => {
      const bubble = document.createElement('article');
      bubble.className = 'message ' + (msg.direction === 'bot' ? 'bot' : 'user');
      const label = document.createElement('strong');
      label.textContent = msg.direction === 'bot' ? 'AI yanıtı' : 'Kullanıcı';
      const time = document.createElement('time'); time.textContent = msg.created_at;
      const body = document.createElement('div'); body.className = 'message-text'; body.textContent = msg.body;
      bubble.append(label, time, body); container.append(bubble);
    });
    if (!records.size) container.textContent = 'Henüz kayıtlı mesaj yok. Eski Telegram geçmişi getirilemez.';
  }
  async function refresh(loadOlder = false) {
    if (busy || document.hidden) return;
    busy = true; older.disabled = true;
    try {
      const after = records.size ? Math.max(...records.keys()) : 0;
      const resp = await fetch('/admin/api/user/' + chat.dataset.user + '/messages' + (loadOlder ? '?before=' + before : '?after=' + after), {cache:'no-store', signal:AbortSignal.timeout(15000)});
      if (resp.status === 401) { records.clear(); container.replaceChildren(); location.assign('/admin'); return; }
      if (!resp.ok) throw new Error('fetch');
      const data = await resp.json();
      if (revision !== data.revision) records.clear();
      revision = data.revision;
      if (!data.enabled) {
        records.clear(); container.replaceChildren();
        container.textContent = 'Sohbet kaydı KAPALI. Kullanıcı tercihi nedeniyle mesajlar gösterilmiyor.';
        status.textContent = 'Kayıt kapalı'; older.hidden = true; before = 0;
      } else {
        data.messages.forEach(msg => records.set(msg.message_id,msg));
        records.forEach((msg,id) => { if (msg.created_ts < Date.now()/1000-30*86400) records.delete(id); });
        before = records.size ? Math.min(...records.keys()) : 0;
        render(); status.textContent = '● Güncel';
        if (loadOlder || !after) older.hidden = !data.has_more;
      }
    } catch (_) { status.textContent = 'Bağlantı bekleniyor; tekrar denenecek'; }
    finally { busy = false; older.disabled = false; }
  }
  older.addEventListener('click', () => refresh(true));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  refresh(); setInterval(() => refresh(), 20000);
})();
