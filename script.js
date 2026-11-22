const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const store={get(k,d){try{return JSON.parse(localStorage.getItem(k))??d}catch{return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
/* one-click pairing: the agent opens this page as .../#token=XXXX ; keep the token, then remove it from the address bar */
(function(){const m=location.hash.match(/token=([\w-]+)/);if(m){store.set('agtoken',m[1]);try{history.replaceState(null,'',location.pathname+location.search)}catch{}}})();
let muted=store.get('muted',false);
const SET=Object.assign({voice:'',rate:1,pitch:.95,lang:'en-IN',wake:false,hud:true,agent:'http://127.0.0.1:8765'},store.get('settings',{}));
const saveSet=()=>store.set('settings',SET);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
/* transcript (kept only in this browser) */
const LOG=store.get('log',[]);
function logMsg(who,text){LOG.push({who,text:String(text).slice(0,400),t:new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})});while(LOG.length>80)LOG.shift();store.set('log',LOG);if($('#p-log').classList.contains('open'))renderLog()}
function renderLog(){const el=$('#logview');el.innerHTML=LOG.length?LOG.map(m=>`<div class="bub ${m.who}"><small>${m.who==='you'?'You':'Jarvis'} · ${esc(m.t)}</small>${esc(m.text)}</div>`).join(''):'<p>No conversation yet.</p>';el.scrollTop=el.scrollHeight}
/* toasts + chime */
function toast(msg,cls=''){const d=document.createElement('div');d.className='toast '+cls;d.textContent=msg;$('#toasts').appendChild(d);setTimeout(()=>d.classList.add('out'),3600);setTimeout(()=>d.remove(),4200)}
function chime(f=880){try{const a=new (window.AudioContext||window.webkitAudioContext)(),o=a.createOscillator(),g=a.createGain();o.frequency.value=f;g.gain.value=.05;o.connect(g);g.connect(a.destination);o.start();g.gain.exponentialRampToValueAtTime(.0001,a.currentTime+.25);o.stop(a.currentTime+.26);setTimeout(()=>a.close(),400)}catch{}}
/* ---------- speech ---------- */
const synth=window.speechSynthesis;let speakingNow=false;
function pickVoice(){const vs=synth?synth.getVoices():[];if(SET.voice){const v=vs.find(v=>v.name===SET.voice);if(v)return v}
  return vs.find(v=>/en-(GB|IN|US)/.test(v.lang)&&/male|daniel|ravi|george|david|google uk english male/i.test(v.name))||vs.find(v=>/^en/.test(v.lang))||null}
function say(t,opts={}){
  $('#reply').textContent=t; clearTimeout(say.t); say.t=setTimeout(()=>$('#reply').textContent='',9000);
  if(!opts.nolog)logMsg('jarvis',t);
  if(muted||!synth)return;
  synth.cancel(); const u=new SpeechSynthesisUtterance(t),v=pickVoice();
  if(v)u.voice=v; u.rate=+SET.rate||1; u.pitch=+SET.pitch||1;
  u.onstart=()=>{speakingNow=true;setOrb('speak');setStatus('Speaking…',1)}; u.onend=()=>{speakingNow=false;if(window.orbState==='speak')setOrb('idle');setStatus('Jarvis Ready')};
  u.onerror=u.onend;
  synth.speak(u);clearTimeout(say.r);say.r=setTimeout(()=>{speakingNow=false;if($('#status').textContent==='Speaking…'){setStatus('Jarvis Ready');if(window.orbState==='speak')setOrb('idle')}},Math.max(3000,t.length*95));
}
function setStatus(t,on){const s=$('#status');s.textContent=t;s.classList.toggle('on',!!on)}
$('#mute').onclick=()=>{muted=!muted;store.set('muted',muted);$('#mute').textContent=muted?'🔇':'🔊';if(muted)synth&&synth.cancel()};
$('#mute').textContent=muted?'🔇':'🔊';
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
let rec,listening=false,recMode='cmd',awaitUntil=0,manualStop=false,cmdPending=false;
function updWake(){const c=$('#wakechip');if(!c)return;c.style.display=SET.wake?'':'none';c.textContent=listening&&recMode==='wake'?'🎧 Say “Jarvis…”':SET.wake?'🎧 Wake word on':'';$('#wakebtn').classList.toggle('on',!!SET.wake)}
if(SR){rec=new SR();rec.interimResults=false;
  rec.onstart=()=>{listening=true;cmdPending=false;if(recMode==='cmd'){setOrb('listen');setStatus('Listening…',1)}updWake()};
  rec.onend=()=>{listening=false;if(recMode==='cmd'&&window.orbState==='listen')setOrb('idle');if($('#status').textContent==='Listening…')setStatus('Jarvis Ready');
    if(SET.wake&&!manualStop&&!cmdPending)setTimeout(()=>{if(!listening)startRec('wake')},500);updWake()};
  rec.onresult=e=>{const r=e.results[e.results.length-1];if(!r.isFinal)return;const t=r[0].transcript.trim();if(!t)return;
    if(recMode==='cmd'){$('#reply').textContent='“'+t+'”';run(t);return}
    if(speakingNow)return;                                     // ignore my own voice
    const m=t.match(/^(?:hey |ok |okay |hi )?jarvis\b[\s,.!?]*(.*)$/i);
    if(m){if(m[1].trim())run(m[1]);else{awaitUntil=Date.now()+9000;chime();setStatus('Yes? I\'m listening…',1)}}
    else if(Date.now()<awaitUntil){awaitUntil=0;run(t)}};
  rec.onerror=e=>{if(e.error==='not-allowed'||e.error==='service-not-allowed'){SET.wake=false;saveSet();updWake();say('Microphone permission was denied.')}
    else if(!['no-speech','aborted'].includes(e.error)&&recMode==='cmd')say('I did not catch that.')};
}
function startRec(mode){if(!rec)return;rec.lang=SET.lang;rec.continuous=mode==='wake';manualStop=false;try{recMode=mode;rec.start()}catch{}}
function toggleMic(){if(window.orbState==='speak')stopAll();
  if(!rec){say('Voice input is not supported in this browser. Use Chrome or Edge, or type a command.');return}
  if(listening){const wasWake=recMode==='wake';cmdPending=wasWake;rec.stop();if(wasWake)setTimeout(()=>{synth&&synth.cancel();startRec('cmd')},350);return}
  try{synth&&synth.cancel()}catch{}startRec('cmd')}
function setWake(on){SET.wake=on;saveSet();if(on){if(!rec){say('Wake word needs Chrome or Edge.');SET.wake=false;saveSet();updWake();return}if(listening){cmdPending=false}else startRec('wake');say('Wake word on. Say Jarvis, then your command.')}
  else{manualStop=true;if(listening&&recMode==='wake')rec.stop();say('Wake word off.')}updWake();const c=$('#setwake');if(c)c.checked=on}
$('#wakebtn').onclick=()=>setWake(!SET.wake);
$('#mic').onclick=toggleMic; $('#core').onclick=()=>{if(window.orbState==='speak'||AG.busy)stopAll();else toggleMic()};
$('#stopbtn').onclick=stopAll;
document.addEventListener('keydown',e=>{
  const typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName);
  if(e.key==='Escape'){stopAll();closePanels();$('#txt').blur()}
  else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('#txt').focus()}
  else if(!typing&&e.key==='/'){e.preventDefault();$('#txt').focus()}
  else if(e.code==='Space'&&!typing){e.preventDefault();toggleMic()}});
/* ---------- data ---------- */
const QUOTES=[["The best way to predict the future is to invent it.","Alan Kay"],["Stay hungry, stay foolish.","Steve Jobs"],["Whether you think you can, or you think you can't — you're right.","Henry Ford"],["Genius is one percent inspiration and ninety-nine percent perspiration.","Thomas Edison"],["Sometimes you gotta run before you can walk.","Tony Stark"],["It always seems impossible until it's done.","Nelson Mandela"],["Simplicity is the ultimate sophistication.","Leonardo da Vinci"]];
let qi=0;
function showQuote(){const q=QUOTES[qi%QUOTES.length];$('#qtext').textContent='“'+q[0]+'”';$('#qby').textContent='— '+q[1];return q}
$('#qnext').onclick=()=>{qi++;const q=showQuote();say(q[0]+' '+q[1])};
const DEF_MODES=[
 {n:'Work Mode',d:'Open your core work sites and get productive.',links:['https://mail.google.com','https://calendar.google.com','https://github.com']},
 {n:'Focus Mode',d:'Open notes and cut distractions.',links:['https://www.google.com/search?q=pomodoro+timer']},
 {n:'Study Mode',d:'Prepare a simple study workspace.',links:['https://www.khanacademy.org','https://www.wikipedia.org']},
 {n:'Research Mode',d:'Start a web search for deep research.',links:['https://scholar.google.com','https://www.wikipedia.org']},
 {n:'Planning Mode',d:'Open planning tools.',links:['https://calendar.google.com','https://keep.google.com']},
 {n:'Creative Mode',d:'Open a blank space and some inspiration.',links:['https://www.pinterest.com','https://dribbble.com']}];
let modes=store.get('modes',DEF_MODES);
function renderModes(){
  $('#modes').innerHTML=modes.map((m,i)=>`<div class="card"><h3>${esc(m.n)}</h3><p>${esc(m.d)}</p><p style="font-size:11px">say: <b>start ${esc(m.n.toLowerCase())}</b> · ${m.links.length} link(s)</p><button class="btn" data-run="${i}">Run</button><button class="btn" data-edit="${i}">Edit</button><button class="btn" data-del="${i}">Delete</button></div>`).join('');
}
function runMode(m){say('Starting '+m.n+'. Opening '+m.links.length+' link'+(m.links.length==1?'':'s')+'.');m.links.forEach((u,i)=>setTimeout(()=>window.open(u,'_blank','noopener'),i*250))}
$('#modes').onclick=e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.run!=null)runMode(modes[b.dataset.run]);
  if(b.dataset.del!=null&&confirm('Delete this mode?')){modes.splice(b.dataset.del,1);store.set('modes',modes);renderModes()}
  if(b.dataset.edit!=null)editMode(+b.dataset.edit)};
function editMode(i){const m=modes[i];const n=prompt('Mode name',m.n);if(!n)return;
  const l=prompt('Website links (comma separated)',m.links.join(', '));if(l===null)return;
  m.n=n;m.links=l.split(',').map(s=>s.trim()).filter(Boolean).map(u=>/^https?:/.test(u)?u:'https://'+u);store.set('modes',modes);renderModes()}
$('#newmode').onclick=()=>{const n=prompt('New mode name');if(!n)return;const l=prompt('Website links (comma separated)','github.com');if(l===null)return;
  modes.push({n,d:'Custom mode.',links:l.split(',').map(s=>s.trim()).filter(Boolean).map(u=>/^https?:/.test(u)?u:'https://'+u)});store.set('modes',modes);renderModes()};
renderModes();
/* ---------- panels ---------- */
function openPanel(id){closePanels();$('#p-'+id).classList.add('open');if(id==='battery')battery();if(id==='sys')sysinfo();if(id==='quotes')showQuote();if(id==='link'){$('#agtoken').value=store.get('agtoken','');ping()}if(id==='memory'){ping()}if(id==='log')renderLog();if(id==='settings')fillSettings();if(id==='profile'){$('#pname').value=store.get('name','');$('#pcity').value=store.get('city','')}}
function closePanels(){$$('.panel').forEach(p=>p.classList.remove('open'))}
$$('[data-close]').forEach(b=>b.onclick=closePanels);
$$('[data-p]').forEach(b=>b.onclick=()=>openPanel(b.dataset.p));
$('#psave').onclick=()=>{store.set('name',$('#pname').value.trim());store.set('city',$('#pcity').value.trim());say('Profile saved.');closePanels()};
let batt=null;
if(navigator.getBattery)navigator.getBattery().then(b=>{batt=b;['levelchange','chargingchange'].forEach(ev=>b.addEventListener(ev,battery))});
function battery(){
  if(!batt){$('#bl').textContent='N/A';$('#bs').textContent='Unavailable';$('#bt').textContent='This browser does not expose battery data.';return null}
  const p=Math.round(batt.level*100);$('#bl').textContent=p+'%';$('#bbar').style.width=p+'%';
  $('#bs').textContent=batt.charging?'Charging':'On battery';
  const sec=batt.charging?batt.chargingTime:batt.dischargingTime;
  $('#bt').textContent=isFinite(sec)&&sec>0?`About ${Math.round(sec/60)} min ${batt.charging?'to full':'remaining'}.`:'';
  return p}
function sysinfo(){
  const c=navigator.connection||{};
  const rows=[['Platform',navigator.userAgentData?.platform||navigator.platform],['CPU threads',navigator.hardwareConcurrency||'?'],['Memory (approx)',navigator.deviceMemory?navigator.deviceMemory+' GB':'n/a'],['Screen',screen.width+'×'+screen.height],['Language',navigator.language],['Network',navigator.onLine?('Online'+(c.effectiveType?' · '+c.effectiveType:'')):'Offline'],['Time zone',Intl.DateTimeFormat().resolvedOptions().timeZone],['Browser',navigator.userAgent.match(/(Edg|Chrome|Firefox|Safari)\/[\d.]+/)?.[0]||'?']];
  $('#sysgrid').innerHTML=rows.map(r=>`<div class="card"><h3>${r[0]}</h3><div style="font-size:20px;color:var(--c2)">${esc(r[1])}</div></div>`).join('');return rows}
/* ---------- themes / code red ---------- */
const HUES=[180,265,140,38,210];let hi=0;
function nextBg(){hi=(hi+1)%HUES.length;document.documentElement.style.setProperty('--h',HUES[hi]);say('Background theme changed.')}
function codeRed(on){$('#red').classList.toggle('on',on);document.body.classList.toggle('red',on);
  if(on){say('Warning. Code Red authorization accepted.');beep()}else say('Standing down. Back to normal.')}
$('#redbtn').onclick=()=>codeRed(true);$('#redoff').onclick=()=>codeRed(false);
function beep(){try{const a=new AudioContext(),o=a.createOscillator(),g=a.createGain();o.type='square';o.frequency.value=520;g.gain.value=.05;o.connect(g);g.connect(a.destination);o.start();
  let t=0;const iv=setInterval(()=>{o.frequency.value=t++%2?520:760;if(t>8){clearInterval(iv);o.stop();a.close()}},220)}catch{}}
/* ---------- brain: command router ---------- */
const SITES={youtube:'https://www.youtube.com',google:'https://www.google.com',github:'https://github.com',gmail:'https://mail.google.com',whatsapp:'https://web.whatsapp.com',instagram:'https://www.instagram.com',twitter:'https://x.com',x:'https://x.com',facebook:'https://www.facebook.com',linkedin:'https://www.linkedin.com',netflix:'https://www.netflix.com',spotify:'https://open.spotify.com',maps:'https://maps.google.com',chatgpt:'https://chatgpt.com',claude:'https://claude.ai',reddit:'https://www.reddit.com',amazon:'https://www.amazon.in',wikipedia:'https://www.wikipedia.org'};
function greet(){const h=new Date().getHours(),n=store.get('name','');return (h<12?'Good morning':h<17?'Good afternoon':'Good evening')+(n?', '+n:'')+'. '+(AG.ok?'Your laptop link is active. ':'Laptop link is offline. ')+'How can I help?'}
/* ---------- orb state ---------- */
function setOrb(s){$('#core').dataset.state=s;window.orbState=s}
setOrb('idle');
function stopAll(){try{synth&&synth.cancel()}catch{}if(listening)try{rec.stop()}catch{}if(AG.ok&&AG.busy)agent({action:'stop'}).catch(()=>{});setOrb('idle');setStatus('Jarvis Ready')}
/* ---------- laptop agent link (talks to agent.py on this laptop) ---------- */
const AG={url:(SET.agent||'http://127.0.0.1:8765').replace(/\/$/,''),ok:false,bad:false,brain:null,busy:false,mem:null,gui:true,seen:null};let pending=null;
const tok=()=>store.get('agtoken','');
async function agent(body){const r=await fetch(AG.url+'/do',{method:'POST',headers:{'Content-Type':'text/plain','X-Jarvis-Token':tok()},body:JSON.stringify(body)});if(r.status===401)throw new Error('token');if(!r.ok)throw new Error('http');return r.json()}
async function ping(){const was=AG.ok;try{const r=await fetch(AG.url+'/ping',{headers:{'X-Jarvis-Token':tok()}});AG.ok=r.ok;AG.bad=r.status===401;if(r.ok){const j=await r.json();AG.brain=j.brain;AG.mem=j.memory;AG.gui=j.gui;renderMem()}else AG.brain=null}catch{AG.ok=false;AG.bad=false;AG.brain=null}
  if(AG.seen!==null&&was!==AG.ok)toast(AG.ok?'Laptop agent connected':'Laptop agent disconnected',AG.ok?'good':'bad');AG.seen=AG.ok;updLink();if(!AG.ok)$('#hud').classList.remove('on')}
function brainText(){const b=AG.brain;if(!AG.ok)return['Brain: offline','bad'];if(!b.ollama)return['Ollama not running','bad'];if(!b.ready)return['Model missing: '+b.model,'bad'];return['Brain: '+b.model,'good']}
function updLink(){
  const set=(el,txt,cls)=>{if(!el)return;el.textContent=txt;el.classList.remove('good','bad');el.classList.add(cls)};
  set($('#agchip'),AG.ok?'● Agent online':AG.bad?'● Wrong token':'● Agent offline',AG.ok?'good':'bad');
  const [bt,bc]=brainText();set($('#brainchip'),bt,bc);
  set($('#linkstat'),AG.ok?'Connected ✔':AG.bad?'Wrong token':'Agent not running',AG.ok?'good':'bad');
  set($('#brainstat'),AG.ok?(AG.brain.ollama?(AG.brain.ready?'Ollama ready ✔ ('+AG.brain.model+')':'Ollama running, model "'+AG.brain.model+'" not installed'):'Ollama is not running'):'unknown (agent offline)',bc);
  renderCheck();
  const hint=$('#brainhint');if(hint)hint.textContent=AG.ok&&AG.brain.ollama&&!AG.brain.ready?'Open a terminal and run: ollama pull '+AG.brain.model:AG.ok&&!AG.brain.ollama?'Start the Ollama app, then wait a few seconds.':'';
}
function renderCheck(){const el=$('#check');if(!el)return;const b=AG.brain,rows=[
  [AG.ok,'Agent running on this laptop',AG.ok?'':'Double-click start_jarvis_agent.bat (Python must be installed).'],
  [AG.ok&&!AG.bad,'Token accepted',AG.bad?'Wrong token. Paste the one from the agent window.':AG.ok?'':'Needs the agent first.'],
  [AG.ok&&b&&b.ollama,'Ollama running',AG.ok&&b&&!b.ollama?'Open the Ollama app and wait a few seconds.':''],
  [AG.ok&&b&&b.ready,'AI model ready'+(b?' ('+b.model+')':''),AG.ok&&b&&b.ollama&&!b.ready?'Run in a terminal:  ollama pull '+b.model:''],
  [AG.ok&&AG.gui,'Keyboard control (typing, shortcuts)',AG.ok&&!AG.gui?'Run:  pip install pyautogui':'']];
  el.innerHTML=rows.map(r=>`<div class="crow ${r[0]?'ok':'no'}"><b>${r[0]?'✔':'○'}</b><span>${r[1]}${r[2]?`<small>${r[2]}</small>`:''}</span></div>`).join('')}
$('#agsave').onclick=async()=>{store.set('agtoken',$('#agtoken').value.trim());await ping();say(AG.ok?'Laptop link established.':AG.bad?'That token is not right.':'I cannot reach the agent. Is it running?')};
ping();setInterval(ping,12000);
function onState(s){const h=$('#hud');if(s.stats&&SET.hud&&AG.ok){h.classList.add('on');const set=(id,v,t)=>{$('#'+id).style.width=v+'%';$('#'+id+'t').textContent=t};set('hcpu',s.stats.cpu,s.stats.cpu+'%');set('hram',s.stats.ram,s.stats.ram+'%');
    const bw=$('#hbatrow');if(s.stats.battery!=null){bw.style.display='';set('hbat',s.stats.battery,s.stats.battery+'%'+(s.stats.plugged?' ⚡':''));$('#hbat').classList.toggle('low',s.stats.battery<20&&!s.stats.plugged)}else bw.style.display='none'}else h.classList.remove('on');
  (s.alerts||[]).forEach(a=>{chime(660);toast('⏰ '+a.text,'good');say(a.text)})}
setInterval(async()=>{if(!AG.ok||AG.busy)return;try{const r=await fetch(AG.url+'/state',{headers:{'X-Jarvis-Token':tok()}});if(r.ok)onState(await r.json())}catch{ping()}},2500);
let poll=null;
function startPoll(){stopPoll();poll=setInterval(async()=>{try{const r=await fetch(AG.url+'/state',{headers:{'X-Jarvis-Token':tok()}});const s=await r.json();onState(s);
  if(s.state==='thinking'){setOrb('think');setStatus('Thinking…',1)}else if(s.state==='executing'){setOrb('exec');setStatus('Working: '+s.detail,1)}}catch{}},350)}
function stopPoll(){clearInterval(poll);poll=null}
function showSteps(steps){const el=$('#steps');if(!el)return;if(!steps||!steps.length){el.innerHTML='';return}
  el.innerHTML=steps.slice(-6).map(s=>`<div class="${s.ok?'ok':'no'}">${s.ok?'✔':'✖'} ${esc(s.tool.replace(/_/g,' '))}: ${esc(s.message)}</div>`).join('');
  clearTimeout(showSteps.t);showSteps.t=setTimeout(()=>el.innerHTML='',25000)}
function askConfirm(msg,p){pending=p;$('#ctext').textContent=msg;$('#confirmbar').classList.add('on');setOrb('confirm');setStatus('Waiting for your OK',1);say(msg+' Say yes to confirm, or no to cancel.');$('#reply').textContent=''}
function hideConfirm(){$('#confirmbar').classList.remove('on')}
$('#cyes').onclick=()=>run('yes');$('#cno').onclick=()=>run('no');
async function act(body){
  if(!AG.ok){say('My laptop link is offline. Start the agent on your laptop, then enter the token in the Laptop panel.');return true}
  if(AG.busy&&(body.action==='think'||body.action==='confirm')){say("I'm still working on the previous request.");return true}
  const brain=body.action==='think'||body.action==='confirm';
  AG.busy=true;setOrb(brain?'think':'exec');setStatus(brain?'Thinking…':'Working…',1);startPoll();
  try{const r=await agent(body);stopPoll();AG.busy=false;setOrb('idle');setStatus('Jarvis Ready');showSteps(r.steps);
    if(r.needs_confirm)askConfirm(r.message,brain?{brain:true}:{tool:body});else say(r.message||'Done.');ping()}
  catch(e){stopPoll();AG.busy=false;setOrb('idle');setStatus('Jarvis Ready');say(e.message==='token'?'The agent rejected my token.':'I lost contact with your laptop.');ping()}
  return true}
const tool=(name,args={})=>act({action:'tool',name,args});
async function rawTool(name,args){try{return await agent({action:'tool',name,args})}catch{ping();return{ok:false,message:'I lost contact with your laptop.'}}}
async function openTarget(k){
  const r=await rawTool('open_app',{name:k});if(r.ok){say(r.message);return true}
  if(SITES[k]){const r2=await rawTool('open_url',{url:SITES[k]});say(r2.ok?'Opening '+k+' in your browser.':r2.message);return true}
  say(r.message);return true}
/* quick, precise commands run instantly; everything else goes to the AI brain */
const simple=k=>/^[\w .+#&'-]{1,40}$/.test(k)&&!/\b(and|then|when|after|before|while|search|visit|with|type|write|for|in|on|to|it|that|this|them|again|my|file|folder)\b/.test(k);
async function local(t){
  let m;
  if(m=t.match(/^(?:set )?volume(?: to)? (\d{1,3})\b/))return tool('set_volume',{level:+m[1]});
  if(/^(volume up|louder|turn it up|increase (the )?volume)$/.test(t))return tool('set_volume',{direction:'up'});
  if(/^(volume down|quieter|turn it down|decrease (the )?volume|lower the volume)$/.test(t))return tool('set_volume',{direction:'down'});
  if(/^(mute|unmute)( the)?( sound| volume| laptop)?$/.test(t))return tool('set_volume',{direction:'mute'});
  if(/^(next (song|track)|skip( this)?( song| track)?)$/.test(t))return tool('media_control',{key:'next'});
  if(/^(previous|last) (song|track)$/.test(t))return tool('media_control',{key:'prev'});
  if(/^(pause|resume|play)( the)?( music| song| video| media)?$/.test(t))return tool('media_control',{key:'play'});
  if(/^(take (a )?|capture (the )?)?(screenshot|screen shot|screen)$/.test(t)||/^take a screenshot/.test(t))return tool('screenshot');
  if(/^lock( the)?( laptop| pc| computer| screen)?$/.test(t))return tool('power',{kind:'lock'});
  if(/^(go to sleep|sleep|put (the )?(laptop|pc|computer) to sleep)$/.test(t))return tool('power',{kind:'sleep'});
  if(/^cancel (the )?(shutdown|restart)$/.test(t))return tool('power',{kind:'cancel_shutdown'});
  if(/^(shut ?down|turn off)( the)?( laptop| pc| computer)?$/.test(t))return tool('power',{kind:'shutdown'});
  if(/^(restart|reboot)( the)?( laptop| pc| computer)?$/.test(t))return tool('power',{kind:'restart'});
  if(/^(sign|log) ?out$/.test(t))return tool('power',{kind:'logoff'});
  if(/^(show (the )?desktop|minimi[sz]e (all|everything))$/.test(t))return tool('press_keys',{keys:'win d'});
  if(/^switch (the )?(window|app)s?$/.test(t))return tool('press_keys',{keys:'alt tab'});
  if(m=t.match(/^(?:type|dictate)\s+(.+)/))return tool('type_text',{text:raw0.replace(/^\s*(?:hey |hi |ok |okay )?jarvis[, ]*/i,'').replace(/^(type|dictate)\s+/i,'')});
  if(m=t.match(/^press\s+([a-z0-9+ ]{1,30})$/))return tool('press_keys',{keys:m[1]});
  if(m=t.match(/^(?:open|show) (?:my |the )?(desktop|documents|downloads|pictures|music|videos|home)(?: folder)?$/))return tool('open_folder',{name:m[1]});
  if(m=t.match(/^open file\s+(.+)/))return tool('find_file',{query:m[1],open:true});
  if(m=t.match(/^(?:find|locate) (?:the )?file\s+(.+)/))return tool('find_file',{query:m[1]});
  if(m=t.match(/^(?:close|quit|kill)\s+(.+)/)){if(simple(m[1]))return tool('close_app',{name:m[1]});return false}
  if(AG.ok&&(m=t.match(/^(?:open|launch|start)\s+(.+)/))){
    const k=m[1].replace(/\.com$/,'').trim();
    if(/ mode$/.test(k)||modes.some(x=>x.n.toLowerCase().replace(' mode','')===k))return false;
    if(!simple(k))return false;
    if(/\.[a-z]{2,}$/.test(m[1])&&!/\s/.test(m[1]))return tool('open_url',{url:m[1]});
    return openTarget(k)}
  return false}
let raw0='';const HIST=LOG.filter(m=>m.who==='you').map(m=>m.text).slice(-30);let hpos=HIST.length;
async function run(raw){
  raw0=raw;if(raw&&raw.trim()){logMsg('you',raw);HIST.push(raw);hpos=HIST.length}
  const t=raw.toLowerCase().replace(/^(hey |hi |ok |okay )?jarvis[, ]*/,'').replace(/[.?!]+$/,'').trim();
  if(pending){const p=pending;pending=null;hideConfirm();
    if(/^(yes|yeah|yep|yup|sure|confirm|do it|go ahead|proceed)\b/.test(t))return act(p.brain?{action:'confirm',approve:true}:{...p.tool,confirm:true});
    if(/^(no|nope|cancel|stop|abort|don'?t)\b/.test(t)){if(p.brain)return act({action:'confirm',approve:false});setOrb('idle');setStatus('Jarvis Ready');return say('Cancelled.')}
    setOrb('idle')}
  if(!t){say(greet());return}
  if(!/^(hello|hi|hey|code red|stand down|what time|what's the time)/.test(t)&&await local(t))return;
  let m;
  if(/^(hello|hi|hey|greeting|good (morning|evening|afternoon))/.test(t))return say(greet());
  if(/code red/.test(t)&&!/(off|stand down)/.test(t))return codeRed(true);
  if(/stand down|code red off|all clear/.test(t))return codeRed(false);
  if(/^(what('s| is) your name|who are you)$/.test(t))return say('I am Jarvis, your personal assistant, running right here in your browser.');
  if(/^how are you/.test(t))return say('Fully operational, and ready for your next order.');
  if(/^(what('s| is)( the)? |what )?(current )?time( is it)?( now)?$/.test(t))return say('It is '+new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})+'.');
  if(/^(what('s| is)( the)? )?(today'?s? )?date( today)?$|^what day( is it)?( today)?$/.test(t))return say('Today is '+new Date().toLocaleDateString([],{weekday:'long',day:'numeric',month:'long',year:'numeric'})+'.');
  if(/^(check |show |what.?s )?(my |the )?battery( level| status)?( now)?$/.test(t)){const p=battery();openPanel('battery');return say(p==null?'Battery information is not available in this browser.':`Battery is at ${p} percent and ${batt.charging?'charging':'running on battery'}.`)}
  if(/^(show |open |check )?(my )?system (info|status)$/.test(t)){const r=sysinfo();openPanel('sys');return say(`You have ${r[1][1]} CPU threads${navigator.deviceMemory?' and about '+navigator.deviceMemory+' gigabytes of memory':''}. Network is ${navigator.onLine?'online':'offline'}.`)}
  if(/^(open |show )?(my )?profile$/.test(t))return(openPanel('profile'),say('Opening your profile.'));
  if(/^(give me |tell me |show )?(me )?(a |an )?(quote|inspiration|motivation)/.test(t)){qi=Math.floor(Math.random()*QUOTES.length);openPanel('quotes');const q=showQuote();return say(q[0]+' — '+q[1])}
  if(/^(change|switch|next)\b.*\b(background|theme|colou?r)/.test(t))return nextBg();
  if(/^(open |show )?(my )?automations?$/.test(t))return(openPanel('auto'),say('Here are your automations.'));
  if(/^launch|launcher/.test(t)&&!/mode/.test(t)){openPanel('auto');return say('Pick a mode to launch, or say start work mode.')}
  if(m=t.match(/(?:start|run|activate|launch|begin)\s+(.+?)(?:\s+mode)?$/)){const k=m[1].replace(/ mode$/,'');const md=modes.find(x=>x.n.toLowerCase().replace(' mode','')===k.trim());if(md)return runMode(md)}
  /* laptop agent online: everything else goes to the AI brain. The lines below are browser-only fallbacks for when it is offline. */
  if(AG.ok&&!/^(thank|.*\bjoke\b)/.test(t)&&!/^(calculate|what is|what's)\s+[\d\s+\-*/().x%^]+$/.test(t))return act({action:'think',text:raw});
  if(m=t.match(/^(?:search|google|look up|find)(?: for)?\s+(.+)/))return(say('Searching for '+m[1]+'.'),window.open('https://www.google.com/search?q='+encodeURIComponent(m[1]),'_blank','noopener'));
  if(m=t.match(/^(?:play|youtube)\s+(.+)/))return(say('Playing '+m[1]+' on YouTube.'),window.open('https://www.youtube.com/results?search_query='+encodeURIComponent(m[1]),'_blank','noopener'));
  if(m=t.match(/^(?:open|go to|visit)\s+(.+)/)){const k=m[1].replace(/\.com$/,'').trim();
    if(SITES[k])return(say('Opening '+k+'.'),window.open(SITES[k],'_blank','noopener'));
    if(/\./.test(m[1]))return(say('Opening '+m[1]+'.'),window.open('https://'+m[1].replace(/\s/g,''),'_blank','noopener'));
    return say("I can open websites, not desktop apps, from a browser. Try 'open youtube' or say a full address.")}
  if(m=t.match(/^(?:calculate|what is|what's)\s+([\d\s+\-*/().x%^]+)$/)){try{const v=Function('"use strict";return ('+m[1].replace(/x/g,'*').replace(/\^/g,'**')+')')();return say('That equals '+v+'.')}catch{}}
  if(/weather/.test(t)){const c=store.get('city','');window.open('https://www.google.com/search?q=weather'+(c?'+'+encodeURIComponent(c):''),'_blank','noopener');return say('Pulling up the weather.')}
  if(/joke/.test(t)){const j=['I would tell you a UDP joke, but you might not get it.','There are 10 kinds of people: those who understand binary and those who do not.','Why do programmers prefer dark mode? Because light attracts bugs.'];return say(j[Math.floor(Math.random()*j.length)])}
  if(/thank/.test(t))return say('Always a pleasure.');
  if(!AG.ok)return say("I only know basic commands while my laptop link is offline. Start the agent and connect it, and I can do anything you ask.");
  return act({action:'think',text:raw});
}
$('#txt').addEventListener('keydown',e=>{if(e.key==='ArrowUp'&&HIST.length){e.preventDefault();hpos=Math.max(0,hpos-1);e.target.value=HIST[hpos]||''}else if(e.key==='ArrowDown'){e.preventDefault();hpos=Math.min(HIST.length,hpos+1);e.target.value=HIST[hpos]||''}});
$('#cmd').onsubmit=e=>{e.preventDefault();const v=$('#txt').value;$('#txt').value='';run(v)};
$$('[data-c]').forEach(b=>b.onclick=()=>run(b.dataset.c));
setInterval(()=>$('#clock').textContent=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),1000);
/* ---------- globe ---------- */
const cv=$('#globe'),cx=cv.getContext('2d');let W,H,DPR;
function size(){DPR=Math.min(devicePixelRatio||1,2);W=cv.width=innerWidth*DPR;H=cv.height=innerHeight*DPR}
addEventListener('resize',size);size();
const PTS=[];const N=2200;
const land=(la,lo)=>Math.sin(la*3+1)*Math.cos(lo*2.3)+Math.sin(lo*4+la*2)*.6+Math.cos(la*5-lo*3)*.35>.35;
for(let i=0;i<N;i++){const y=1-2*(i+.5)/N,r=Math.sqrt(1-y*y),th=i*2.399963;
  const la=Math.asin(y),lo=th%(Math.PI*2);PTS.push({x:Math.cos(th)*r,y,z:Math.sin(th)*r,L:land(la,lo)})}
const STARS=Array.from({length:140},()=>({x:Math.random(),y:Math.random(),s:Math.random()*1.5+.3,p:Math.random()*6}));
const RINGS=Array.from({length:6},(_,i)=>({a:Math.random()*3,b:.25+Math.random()*.5,rot:Math.random()*6,sp:(Math.random()-.5)*.004,ph:Math.random()*6,k:1.15+i*.04}));
let rot=0;
function frame(t){
  cx.clearRect(0,0,W,H);
  const hue=getComputedStyle(document.documentElement).getPropertyValue('--h')||180;
  const h=document.body.classList.contains('red')?355:+hue;
  const col=(a,l=60)=>`hsla(${h},100%,${l}%,${a})`;
  STARS.forEach(s=>{cx.fillStyle=col(.3+.3*Math.sin(t/900+s.p),80);cx.fillRect(s.x*W,s.y*H,s.s*DPR,s.s*DPR)});
  const R=Math.min(W,H)*.3,X=W/2,Y=H*.46;rot+=.003;
  const g=cx.createRadialGradient(X,Y,R*.6,X,Y,R*1.35);g.addColorStop(0,col(.18,40));g.addColorStop(1,col(0));cx.fillStyle=g;cx.beginPath();cx.arc(X,Y,R*1.35,0,7);cx.fill();
  cx.strokeStyle=col(.35);cx.lineWidth=1.5*DPR;cx.beginPath();cx.arc(X,Y,R,0,7);cx.stroke();
  const tilt=.4,ct=Math.cos(tilt),st=Math.sin(tilt),cr=Math.cos(rot),sr=Math.sin(rot);
  for(const p of PTS){
    let x=p.x*cr+p.z*sr,z=-p.x*sr+p.z*cr,y=p.y;
    const y2=y*ct-z*st,z2=y*st+z*ct;
    if(z2<-.05)continue;
    const a=(.15+.85*z2)*(p.L?1:.28);
    cx.fillStyle=col(a,p.L?70:55);const s=(p.L?2:1.2)*DPR;cx.fillRect(X+x*R,Y+y2*R,s,s)}
  RINGS.forEach(r=>{r.rot+=r.sp;
    cx.strokeStyle=col(.22);cx.lineWidth=DPR;cx.save();cx.translate(X,Y);cx.rotate(r.rot);
    cx.beginPath();cx.ellipse(0,0,R*r.k,R*r.k*r.b,r.a,0,7);cx.stroke();
    const ang=t/1800+r.ph,ex=Math.cos(ang)*R*r.k,ey=Math.sin(ang)*R*r.k*r.b;
    cx.rotate(r.a);cx.rotate(-r.a);
    const ca=Math.cos(r.a),sa=Math.sin(r.a);
    cx.fillStyle=col(1,80);cx.beginPath();cx.arc(ex*ca-ey*sa,ex*sa+ey*ca,3*DPR,0,7);cx.fill();cx.restore()});
  requestAnimationFrame(frame)}
requestAnimationFrame(frame);
/* ---------- boot ---------- */
const LINES=['[BOOT] Initializing Jarvis core…','[POWER] Primary power path stable.','[VOICE] Speech engine '+(SR?'online.':'unavailable (type commands).'),'[AUDIO] Voice output '+(synth?'ready.':'unavailable.'),()=>AG.ok?'[AGENT] Laptop agent online, token accepted.':AG.bad?'[AGENT] Agent found but the token is wrong.':'[AGENT] Laptop agent offline. Start it to control your PC.','[AUTOMATION] Loading '+modes.length+' workflow modes…',()=>!AG.ok?'[BRAIN] Waiting for the agent…':!AG.brain.ollama?'[BRAIN] Ollama is not running.':!AG.brain.ready?'[BRAIN] Model missing: '+AG.brain.model:'[BRAIN] Ollama ready: '+AG.brain.model,'[PROFILE] Loading local profile.','[SECURITY] Code Red protocol armed.','[GUARD] Stability guard nominal.','[READY] Jarvis is online.'];
let bi=0;const con=$('#console'),bc=$('#bc'),bp=$('#bp');
const bt=setInterval(()=>{bi++;const p=Math.min(100,Math.round(bi/LINES.length*100));bc.style.strokeDashoffset=327*(1-p/100);bp.textContent=p+'%';
  con.innerHTML=LINES.slice(0,bi).map(l=>(typeof l==='function'?l():l).replace(/^(\[\w+\])/,'<b>$1</b>')).join('<br>');
  if(bi>=LINES.length){clearInterval(bt);$('#bootbtn').style.display='block'}},330);
$('#bootbtn').onclick=()=>{$('#boot').classList.add('hide');setTimeout(()=>$('#boot').remove(),900);
  if(synth)synth.getVoices();setTimeout(()=>say(greet()),400);setTimeout(firstRunCheck,2500);if(SET.wake&&rec)setTimeout(()=>startRec('wake'),1500)};
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&$('#boot')&&$('#bootbtn').style.display==='block')$('#bootbtn').click()});
if(synth)synth.onvoiceschanged=()=>{};

/* ---------- memory panel ---------- */
function renderMem(){const el=$('#memview');if(!el)return;const m=AG.mem;
  if(!AG.ok||!m){el.innerHTML='<p>Connect the laptop agent to see memory.</p>';return}
  const facts=Object.entries(m.facts);
  el.innerHTML='<h3>Remembered facts</h3>'+(facts.length?facts.map(([k,v])=>`<div class="mrow"><span><b>${esc(k)}</b>: ${esc(v)}</span><button data-forget="${esc(k)}">Forget</button></div>`).join(''):'<p>Nothing yet. Say “remember that my favourite editor is VS Code”.</p>')
   +'<h3>Recent actions</h3>'+(m.actions.length?m.actions.slice().reverse().map(a=>`<div class="mrow"><span>${a.ok?'✔':'✖'} ${esc(a.t)} · ${esc(a.tool.replace(/_/g,' '))} ${esc(Object.values(a.args).join(' '))}</span></div>`).join(''):'<p>None.</p>')
   +`<p style="margin-top:12px">${m.turns} conversation turn(s) kept on this laptop.</p>`}
$('#memview').onclick=async e=>{const b=e.target.closest('[data-forget]');if(!b)return;try{const r=await agent({action:'memory',op:'forget',key:b.dataset.forget});AG.mem=r.memory;renderMem()}catch{}};
$('#memclear').onclick=async()=>{if(!confirm('Erase everything JARVIS remembers on this laptop?'))return;try{const r=await agent({action:'memory',op:'clear',scope:'all'});AG.mem=r.memory;renderMem();say('Memory cleared.')}catch{say('I could not reach the agent.')}};
/* ---------- orb waveform ring (idle / listening / thinking / speaking / executing / confirm) ---------- */
(function(){
  const c=$('#orbwave'),x=c.getContext('2d'),N=96,R=92;let ph=0;
  const hue=()=>document.body.classList.contains('red')?355:+(getComputedStyle(document.documentElement).getPropertyValue('--h')||180);
  function frame(t){
    const s=window.orbState||'idle';x.clearRect(0,0,360,360);
    const h=s==='confirm'?45:hue(),amp={idle:1.5,listen:9,think:3,exec:4,speak:14,confirm:2}[s]??1.5;
    ph+=s==='think'?.08:s==='exec'?.14:.04;
    x.lineWidth=2;x.strokeStyle=`hsla(${h},100%,${s==='exec'?85:62}%,.9)`;x.shadowColor=`hsl(${h} 100% 55%)`;x.shadowBlur=10;
    x.beginPath();
    for(let i=0;i<=N;i++){const a=i/N*Math.PI*2;let r=R;
      if(s==='speak')r+=amp*(Math.sin(a*7+ph*6)*.5+Math.sin(a*13-ph*9)*.3+Math.sin(t/90+i)*.2)*(.6+.4*Math.sin(t/160));
      else if(s==='listen')r+=amp*Math.abs(Math.sin(a*9+ph*5))*(.5+.5*Math.sin(t/120));
      else r+=amp*Math.sin(a*5+ph*3)*.5+Math.sin(t/1200)*1.2;
      const px=180+Math.cos(a)*r,py=180+Math.sin(a)*r;i?x.lineTo(px,py):x.moveTo(px,py)}
    x.stroke();
    if(s==='think'||s==='exec'){x.shadowBlur=14;x.lineWidth=4;x.strokeStyle=`hsla(${h},100%,80%,.95)`;
      for(let k=0;k<(s==='exec'?3:1);k++){const a0=ph*(s==='exec'?2.5:1.6)+k*Math.PI*2/3;x.beginPath();x.arc(180,180,R+10,a0,a0+.7);x.stroke()}}
    requestAnimationFrame(frame)}
  requestAnimationFrame(frame)})();

/* ---------- rotating hints in the command box ---------- */
(function(){const H=['Open Chrome, visit YouTube and search for Python tutorials','What’s the weather in Mumbai?','Find my latest PDF','Create a folder named Projects on my desktop','Remind me in 10 minutes to stretch','Set volume to 40','Open Notepad and type hello team','Which apps do I have with “code” in the name?','Take a screenshot'];let i=0;
  setInterval(()=>{if(document.activeElement.id==='txt')return;$('#txt').placeholder='Try: '+H[i++%H.length]},4000);$('#txt').placeholder='Try: '+H[0]})();
/* ---------- settings panel ---------- */
function fillSettings(){const sel=$('#setvoice'),vs=synth?synth.getVoices():[];
  sel.innerHTML='<option value="">Automatic</option>'+vs.map(v=>`<option value="${esc(v.name)}"${v.name===SET.voice?' selected':''}>${esc(v.name)} (${esc(v.lang)})</option>`).join('');
  $('#setrate').value=SET.rate;$('#setpitch').value=SET.pitch;$('#setlang').value=SET.lang;$('#setwake').checked=!!SET.wake;$('#sethud').checked=!!SET.hud;$('#setagent').value=SET.agent;
  $('#ratev').textContent=(+SET.rate).toFixed(2);$('#pitchv').textContent=(+SET.pitch).toFixed(2)}
if(synth)synth.onvoiceschanged=()=>{if($('#p-settings').classList.contains('open'))fillSettings()};
$('#setvoice').onchange=e=>{SET.voice=e.target.value;saveSet()};
$('#setrate').oninput=e=>{SET.rate=+e.target.value;$('#ratev').textContent=SET.rate.toFixed(2);saveSet()};
$('#setpitch').oninput=e=>{SET.pitch=+e.target.value;$('#pitchv').textContent=SET.pitch.toFixed(2);saveSet()};
$('#setlang').onchange=e=>{SET.lang=e.target.value;saveSet();if(rec)rec.lang=SET.lang};
$('#setwake').onchange=e=>setWake(e.target.checked);
$('#sethud').onchange=e=>{SET.hud=e.target.checked;saveSet();if(!SET.hud)$('#hud').classList.remove('on')};
$('#setagent').onchange=e=>{SET.agent=e.target.value.trim()||'http://127.0.0.1:8765';saveSet();AG.url=SET.agent.replace(/\/$/,'');ping()};
$('#settest').onclick=()=>say('Hello. All systems are online. This is how I sound.',{nolog:true});
$('#logclear').onclick=()=>{LOG.length=0;store.set('log',LOG);HIST.length=0;hpos=0;renderLog()};
/* ---------- install as an app (PWA) ---------- */
let deferredInstall=null;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e;$('#installbtn').style.display=''});
$('#installbtn').onclick=async()=>{if(!deferredInstall)return;deferredInstall.prompt();await deferredInstall.userChoice;deferredInstall=null;$('#installbtn').style.display='none'};
if('serviceWorker' in navigator&&(location.protocol==='https:'||location.hostname==='localhost')){navigator.serviceWorker.register('sw.js').catch(()=>{})}
/* ---------- first run: open the setup checklist if something is missing ---------- */
function firstRunCheck(){if(sessionStorage.getItem('setupShown'))return;
  const ready=AG.ok&&AG.brain&&AG.brain.ready&&AG.gui;if(!ready){try{sessionStorage.setItem('setupShown','1')}catch{}openPanel('link')}}
