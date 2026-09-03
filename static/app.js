const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const pages={dashboard:['Preserve your timeline.','Correct Takeout dates, organize your archive, and keep your memories in order.'],source:['Source & output.','Choose what to process and exactly where the organized archive should be written.'],timestamps:['Restore the original dates.','Choose the date structure and duplicate policy.'],metadata:['Preserve corrected metadata.','Filesystem dates are restored automatically; media metadata is optional.'],organization:['Organize with confidence.','Review how the archive will be structured.'],settings:['Final review.','Check everything once before processing.'],processing:['Processing archive.','Watch the local engine work through your Takeout media.']};
let jobId=null,scanId=null,sourceLabel='',selectedFiles=[],sourceGroups=[];
function gotoPage(p){$$('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===p));$$('.page').forEach(x=>x.classList.remove('active'));$('#'+p).classList.add('active');$('#pageTitle').textContent=pages[p][0];$('#pageSub').textContent=pages[p][1];updateSummary()}
$$('.nav').forEach(b=>b.onclick=()=>gotoPage(b.dataset.page));
function toast(t){const x=$('#toast');x.textContent=t;x.classList.add('show');clearTimeout(window.__toast);window.__toast=setTimeout(()=>x.classList.remove('show'),2800)}
function theme(t){document.documentElement.dataset.theme=t;localStorage.setItem('photochronicle-theme',t);$$('[data-theme-choice]').forEach(b=>b.classList.toggle('active',b.dataset.themeChoice===t))}
theme(localStorage.getItem('photochronicle-theme')||'sage');$$('[data-theme-choice]').forEach(b=>b.onclick=()=>theme(b.dataset.themeChoice));
async function health(){try{const d=await (await fetch('/health')).json();$('#healthDot').style.background='#69a474';$('#healthText').textContent='Local service ready';$('#exifStatus').textContent=d.exiftool?'ExifTool is ready':'ExifTool not found';$('#exifPill').textContent=d.exiftool?'Local ExifTool ready':'ExifTool unavailable'}catch{$('#healthDot').style.background='#c96f67';$('#healthText').textContent='Local service unavailable'}} health();
function setStats(d){$('#scanMedia').textContent=(d.media||0).toLocaleString();$('#scanJson').textContent=(d.json||0).toLocaleString();$('#scanAll').textContent=(d.files||0).toLocaleString();const ex=d.extensions||{};const names=Object.keys(ex).sort().map(k=>`${k.toUpperCase()} × ${ex[k].toLocaleString()}`);$('#scanFormats').textContent=names.length?names.join('  ·  '):'No supported photo/video formats detected.'}
function rootName(files){return files[0]?.webkitRelativePath?.split('/')[0]||files[0]?.name||'Source folder'}
function formatGB(n){return (n/1073741824).toFixed(2)+' GB'}
function renderSources(){
 const box=$('#sourceList'); if(!box)return;
 if(!sourceGroups.length){box.innerHTML='<div class="sourceEmpty">No source folders added yet.</div>';} else {
   box.innerHTML=sourceGroups.map((g,i)=>`<div class="sourceItem"><div><strong>${escapeHtml(g.name)}</strong><small>${g.files.length.toLocaleString()} files · ${formatGB(g.bytes)}</small></div><button class="iconBtn" type="button" data-remove-source="${i}" aria-label="Remove ${escapeHtml(g.name)}">×</button></div>`).join('');
   box.querySelectorAll('[data-remove-source]').forEach(b=>b.onclick=()=>removeSource(Number(b.dataset.removeSource)));
 }
 const all=sourceGroups.reduce((n,g)=>n+g.files.length,0), bytes=sourceGroups.reduce((n,g)=>n+g.bytes,0);
 sourceLabel=sourceGroups.length===1?sourceGroups[0].name:`${sourceGroups.length} source folders`;
 $('#sourceName').textContent=sourceGroups.length?sourceLabel:'No folders selected';
 if(!scanId && sourceGroups.length) $('#sourceHint').textContent=`${all.toLocaleString()} files · ${formatGB(bytes)} · ready to scan`;
}
function uniqueRoot(name){let base=name||'Source', candidate=base, n=2;const used=new Set(sourceGroups.map(g=>g.name.toLowerCase()));while(used.has(candidate.toLowerCase())) candidate=`${base} (${n++})`;return candidate}
function withRelativePath(file,rel){try{Object.defineProperty(file,'webkitRelativePath',{value:rel,configurable:true});}catch{}return file}
async function uploadGroup(group, groupIndex){
 const files=group.files,totalBytes=files.reduce((n,f)=>n+(f.size||0),0),BATCH_BYTES=500*1024*1024;
 const batches=[];let batch=[],batchBytes=0;
 for(const f of files){const size=f.size||0;if(batch.length&&batchBytes+size>BATCH_BYTES){batches.push(batch);batch=[];batchBytes=0}batch.push(f);batchBytes+=size;if(size>=BATCH_BYTES){batches.push(batch);batch=[];batchBytes=0}}
 if(batch.length)batches.push(batch);
 let last=null;
 for(let i=0;i<batches.length;i++){
   const fd=new FormData();if(scanId)fd.append('scan_id',scanId);
   batches[i].forEach(f=>fd.append('files',f,f.webkitRelativePath||f.name));
   $('#sourceHint').textContent=`Scanning ${group.name} · batch ${(i+1).toLocaleString()} / ${batches.length.toLocaleString()} · source ${groupIndex+1} / ${sourceGroups.length}…`;
   const r=await fetch('/api/scan',{method:'POST',body:fd});let d={};try{d=await r.json()}catch{}
   if(r.status===413)throw Error('A 500 MB upload batch was rejected. Restart PhotoChronicle and try again.');
   if(!r.ok)throw Error(d.error||'Scan failed');
   scanId=d.scan_id;last=d;setStats(d);
 }
 return last;
}
async function addSourceFiles(files){
 if(!files.length)return;
 const root=uniqueRoot(rootName(files));
 const normalized=files.map(f=>withRelativePath(f,`${root}/${f.webkitRelativePath?.split('/').slice(1).join('/')||f.name}`));
 const bytes=normalized.reduce((n,f)=>n+(f.size||0),0);
 sourceGroups.push({name:root,files:normalized,bytes});selectedFiles=sourceGroups.flatMap(g=>g.files);renderSources();gotoPage('source');
 try{
   let last=await uploadGroup(sourceGroups[sourceGroups.length-1],sourceGroups.length-1);
   if(last){$('#sourceHint').textContent=`${last.media.toLocaleString()} media · ${last.json.toLocaleString()} JSON · ${formatGB(sourceGroups.reduce((n,g)=>n+g.bytes,0))} across ${sourceGroups.length} source folder${sourceGroups.length===1?'':'s'}`;toast(`${root} added and scanned.`)}
 }catch(e){
   sourceGroups.pop();selectedFiles=sourceGroups.flatMap(g=>g.files);renderSources();
   if(scanId){fetch('/api/cleanup-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_id:scanId})}).catch(()=>{});scanId=null;}
   $('#sourceHint').textContent='Scan failed. No files were processed.';toast(e.message)
 }
}
async function removeSource(index){
 if(index<0||index>=sourceGroups.length)return;
 if(scanId){fetch('/api/cleanup-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_id:scanId})}).catch(()=>{});scanId=null;}
 sourceGroups.splice(index,1);selectedFiles=sourceGroups.flatMap(g=>g.files);renderSources();setStats({media:0,json:0,files:0,extensions:{}});
 if(sourceGroups.length){try{for(let i=0;i<sourceGroups.length;i++)await uploadGroup(sourceGroups[i],i);toast('Source list rescanned.')}catch(e){sourceGroups=[];selectedFiles=[];renderSources();toast(e.message)}}
}
async function clearSources(){if(scanId){fetch('/api/cleanup-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_id:scanId})}).catch(()=>{});scanId=null}sourceGroups=[];selectedFiles=[];sourceLabel='';renderSources();setStats({media:0,json:0,files:0,extensions:{}});$('#sourceHint').textContent='Add a folder to begin the local scan.';toast('All source folders cleared.')}
$$('#chooseBtn, #addSourceBtn, #changeSource').forEach(b=>{if(b)b.onclick=()=>$('#folderInput').click()});$('#clearSourcesBtn').onclick=clearSources;$('#folderInput').onchange=e=>{addSourceFiles([...e.target.files]);e.target.value='';};
const dz=$('#dropzone');['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('drag')}));['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('drag')}));
dz.addEventListener('drop',async e=>{const items=[...e.dataTransfer.items],files=[];async function walk(entry,path=''){if(entry.isFile){await new Promise(res=>entry.file(f=>{Object.defineProperty(f,'webkitRelativePath',{value:path+f.name});files.push(f);res()}))}else if(entry.isDirectory){const reader=entry.createReader();await new Promise(resolve=>{const all=[];const read=()=>reader.readEntries(async ents=>{if(!ents.length){for(const x of all)await walk(x,path+entry.name+'/');resolve()}else{all.push(...ents);read()}},()=>resolve());read()})}}try{for(const i of items){const en=i.webkitGetAsEntry?.();if(en)await walk(en)}if(files.length)await addSourceFiles(files);else toast('Drop a folder onto the drop zone.')}catch(err){toast('Could not read dropped folder: '+err.message)}});
$('#chooseOutput').onclick=async()=>{try{const d=await(await fetch('/api/choose-output',{method:'POST'})).json();if(d.path){$('#outputPath').textContent=d.path;updateSummary();toast('Output folder selected.')}}catch{toast('Could not open the Windows folder picker.')}};
$('#continueBtn').onclick=()=>{if(!scanId)return toast('Add and scan at least one Takeout folder first.');if($('#outputPath').textContent==='Not selected')return toast('Choose an output folder first.');gotoPage('timestamps')};
function updateTree(){const v=$('#structure').value;let t='PhotoChronicle Output/\n';if(v==='YYYY-MM-DD')t+='├── 2024-06-14/\n│   └── photo.jpg\n';else if(v==='YYYY')t+='├── 2024/\n│   └── photo.jpg\n';else if(v==='YYYY/MM')t+='├── 2024/\n│   └── 06/\n│       └── photo.jpg\n';else t+='├── 2024/\n│   └── 06/\n│       └── 14/\n│           └── photo.jpg\n';t+='└── NO JSON FILES/';$('#tree').textContent=t}
$('#structure').onchange=()=>{updateTree();updateSummary()};['#duplicates','#useExif','#writeMeta','#copyMode','#confirmStart'].forEach(s=>$(s).addEventListener('change',updateSummary));
$('#timestampsBack').onclick=()=>gotoPage('source');$('#timestampsNext').onclick=()=>gotoPage('metadata');$('#metadataBack').onclick=()=>gotoPage('timestamps');$('#metadataNext').onclick=()=>gotoPage('organization');$('#organizationBack').onclick=()=>gotoPage('metadata');$('#reviewBtn').onclick=()=>gotoPage('settings');$('#reviewBack').onclick=()=>gotoPage('organization');
function updateSummary(){if(!$('#structure'))return;$('#orgStructure').textContent=$('#structure').value;$('#finalCheck').innerHTML=`<div><span>Source</span><b>${escapeHtml(sourceLabel||'Not selected')}</b></div><div><span>Output</span><b>${escapeHtml($('#outputPath').textContent)}</b></div><div><span>Structure</span><b>${escapeHtml($('#structure').value)}</b></div><div><span>Duplicates</span><b>${escapeHtml($('#duplicates').selectedOptions[0].textContent)}</b></div><div><span>Media metadata</span><b>${$('#useExif').checked&&$('#writeMeta').checked?'Enabled':'Disabled'}</b></div><div><span>Operation</span><b>${escapeHtml($('#copyMode').selectedOptions[0].textContent)}</b></div>`}
function clearConsole(){ $('#log').innerHTML=''; }
function addLogs(logs){const box=$('#log');box.innerHTML='';(logs||[]).forEach(x=>{const d=document.createElement('div');d.className='logline';d.innerHTML=`<time>${x.time}</time><em class="${String(x.level).toLowerCase()}">${x.level}</em><span>${escapeHtml(x.message)}</span>`;box.appendChild(d)});box.scrollTop=box.scrollHeight}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}
$('#startBtn').onclick=async()=>{if(!scanId){toast('Select a source folder first.');gotoPage('source');return}if($('#outputPath').textContent==='Not selected'){toast('Choose an output folder first.');gotoPage('source');return}if($('#confirmStart').checked&&!confirm('Start PhotoChronicle processing with the current settings?'))return;const opts={structure:$('#structure').value,duplicates:$('#duplicates').value,useExif:$('#useExif').checked,writeMeta:$('#writeMeta').checked,copyMode:$('#copyMode').value,outputPath:$('#outputPath').textContent};gotoPage('processing');clearConsole();try{const r=await fetch('/api/start-scan-job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_id:scanId,options:opts})}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not start');jobId=d.job_id;$('#cancelBtn').disabled=false;poll()}catch(e){toast(e.message)}};
async function poll(){if(!jobId)return;try{const d=await(await fetch('/api/status/'+jobId)).json();$('#bar').style.width=(d.percent||0)+'%';$('#percent').textContent=(d.percent||0)+'%';$('#count').textContent=`${d.current||0} / ${d.total||0} files`;$('#operation').textContent=d.operation||'Working';$('#currentFile').textContent=d.file||d.message||'';$('#procMessage').textContent=d.message||'Processing…';addLogs(d.logs);if(d.status==='complete'||d.status==='cancelled'){finish(d);return}if(d.status==='error'){addLogs(d.logs);$('#cancelBtn').disabled=true;toast(d.message);return}setTimeout(poll,450)}catch{setTimeout(poll,1000)}}
function finish(d){$('#cancelBtn').disabled=true;const s=d.stats||{};if(d.status!=='complete'){toast('Processing cancelled. Temporary files were cleaned.');return}$('#successText').textContent=`${s.fixed||0} media files were organized. Your source archive was left untouched.`;$('#modalStats').innerHTML=[['Processed',s.fixed||0],['No JSON',s.no_json||0],['Dates fixed',s.filesystem_dates||0],['EXIF written',s.exif_written||0],['Skipped',s.skipped||0],['Live pairs',s.live_pairs||0]].map(x=>`<div><b>${x[1]}</b><span>${x[0]}</span></div>`).join('');$('#successModal').classList.add('show');$('#successModal').setAttribute('aria-hidden','false');$('#modalOpen').onclick=()=>openOutput(d.output_path||$('#outputPath').textContent)}
async function openOutput(path){try{const r=await fetch('/api/open-output',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})}),d=await r.json();if(!r.ok)throw Error(d.error||'Could not open output')}catch(e){toast(e.message)}}
$('#cancelBtn').onclick=async()=>{if(jobId){await fetch('/api/cancel/'+jobId,{method:'POST'});toast('Cancellation requested…')}};$('#clearConsole').onclick=clearConsole;$('#modalClose').onclick=()=>{$('#successModal').classList.remove('show');$('#successModal').setAttribute('aria-hidden','true');gotoPage('dashboard')};
updateTree();updateSummary();
