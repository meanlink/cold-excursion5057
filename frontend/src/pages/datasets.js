import {datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';
export async function dataPage(){
 workspace.datasets=await datasets.list();
 if(!workspace.datasets.some(d=>d.id===workspace.selectedDataset))workspace.selectedDataset=workspace.datasets.length?workspace.datasets[0].id:null;
 let selected=workspace.selectedDataset?await datasets.get(workspace.selectedDataset):null,m=workspace.meta;
 return heading('02 / DATA INTAKE','数据接入与批次追溯','保留原始业务字段、来源和内容指纹。分析任务始终绑定一个数据批次；补传只追加样本，不改写已有调查结论。')+'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>业务批次</h2><span>'+workspace.datasets.length+' 批</span></div><div class="batch-list">'+workspace.datasets.map(d=>'<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+'</strong><span>'+d.rows+' 条 · '+esc(d.source)+'</span><small>SHA256 '+esc(d.checksum.slice(0,18))+'…</small></button>').join('')+'</div><div class="section-title"><h2>接入新数据</h2></div><form id="dataset-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月复测批次"></label><label>上传 CSV 或 JSON<input type="file" id="file-input" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="6" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。5–5,000 条记录。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>校验并接入批次</button></form></section><section class="panel"><div class="section-title"><h2 id="preview-name">'+esc(selected?.name||'尚无批次')+'</h2><span>预览前 30 条</span></div><div id="data-preview">'+table(m.columns,selected?.records.slice(0,30)||[])+'</div>'+(selected?'<div class="section-title"><h2>补传记录到当前批次</h2><span>乱序记录按分钟归位</span></div><form id="supplement-form"><label>上传 CSV 或 JSON<input type="file" id="supplement-file" accept=".json,.csv"></label><label>补传记录 JSON<textarea name="records" rows="4" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">同路线同采样点的相同记录只算一次；分钟或温度不一致视为冲突，整批拒绝。已完成的调查与分发文件保持原值。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>合并补传记录</button></form>':'')+'</section></div>';
}
export function bindData(refresh){
 let source='manual.json';
 const readFile=async(input,fill)=>{try{const file=input.files[0];if(!file)return;const text=await file.text();fill(file,file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text));}catch(error){notify(error.message,true);}};
 document.querySelector('#file-input').addEventListener('change',e=>readFile(e.target,(file,records)=>{source=file.name;document.querySelector('#dataset-form [name=records]').value=JSON.stringify(records,null,2);}));
 document.querySelector('#supplement-file')?.addEventListener('change',e=>readFile(e.target,(file,records)=>{document.querySelector('#supplement-form [name=records]').value=JSON.stringify(records,null,2);}));
 document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{try{const d=await datasets.get(button.dataset.dataset);workspace.selectedDataset=d.id;document.querySelector('#preview-name').textContent=d.name;document.querySelector('#data-preview').innerHTML=table(workspace.meta.columns,d.records.slice(0,30));}catch(error){notify(error.message,true);}});
 submit(document.querySelector('#dataset-form'),async f=>{await datasets.create({name:f.get('name'),source,records:JSON.parse(f.get('records'))});notify('数据已接入，可前往工作台执行分析');await refresh();});
 const supplementForm=document.querySelector('#supplement-form');
 if(supplementForm)submit(supplementForm,async f=>{const r=await datasets.supplement(workspace.selectedDataset,{records:JSON.parse(f.get('records'))});notify('已合并补传：新增 '+r.added+' 条，去重 '+r.deduplicated+' 条');await refresh();});
}
