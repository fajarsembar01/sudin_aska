const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture() {
  const ids = new Map();
  function element() {
    const classes = new Set();
    return {value:'', textContent:'', dataset:{}, children:[], hidden:true,
      classList:{toggle(name,on){if(on===undefined) on=!classes.has(name);on?classes.add(name):classes.delete(name);return on},contains:n=>classes.has(n)},
      append(...children){this.children.push(...children);children.forEach(c=>{if(c.id) ids.set(c.id,c)})},
      remove(){if(this.id) ids.delete(this.id);this.removed=true},scrollIntoView(){},setAttribute(){},
      addEventListener(name,callback){this[name]=callback}};
  }
  const status=element(),issues=element(),resultLink=element(),note=element(),presence=element();
  presence.dataset.roomId='7';
  ids.set('teamSyncStatus',status);ids.set('teamSyncConflicts',issues);ids.set('teamResultLink',resultLink);
  const buttons=[1,2,3,4,5].map(score=>Object.assign(element(),{dataset:{score:String(score)}}));
  const group={querySelectorAll(){return buttons}};
  const form=element(),submitButton=element();
  const snapshot={status:'draft',versions:[],scores:[],notes:[],photos:[],presence:[],view_url:'/result'};
  const requests=[];
  let fail=false;
  const context={document:{
    getElementById(id){return ids.get(id)},createElement:element,
    querySelector(s){if(s.includes('.score-group')) return group;if(s.includes('textarea'))return note;return null},
    querySelectorAll(s){if(s==='.team-room-presence')return [presence];if(s.includes('#submitAssessmentForm,'))return [form];if(s.includes('button'))return [submitButton];return []},
    addEventListener(){}},
    crypto:{randomUUID:()=> 'tab-a'},Map,Set,Number,String,Promise,Error,
    fetch:async (endpoint,options)=>{
      const data=JSON.parse(options.body);requests.push({endpoint,data});
      if(fail)throw new Error('Offline');
      if(endpoint==='/state')return {ok:true,status:200,json:async()=>structuredClone({...snapshot,success:true})};
      const key=data.aspect_id?`score:${data.aspect_id}`:'note';
      const version=snapshot.versions.find(v=>v.field_key===key)?.version||0;
      if(data.base_version!==version)return {ok:false,status:409,json:async()=>({success:false,message:'Conflict'})};
      snapshot.versions=snapshot.versions.filter(v=>v.field_key!==key);
      snapshot.versions.push({school_room_id:7,field_key:key,version:version+1});
      return {ok:true,status:200,json:async()=>({success:true,version:version+1})};
    },window:{addEventListener(){},setInterval(){return 1},clearInterval(){},updateAssessmentAllGroups(){}}};
  vm.runInNewContext(fs.readFileSync('dashboard/static/js/panbers-team.js','utf8'),context);
  const client=context.window.createPanbersTeamClient({initial:structuredClone(snapshot),stateUrl:'/state',csrf:'csrf',userId:1,viewUrl:'/result'});
  const flush=()=>new Promise(resolve=>setImmediate(resolve));
  return {client,snapshot,requests,status,issues,buttons,note,presence,resultLink,form,submitButton,flush,setOffline:v=>{fail=v}};
}

test('remote scores, notes, presence and photo versions update without writing them back',async()=>{
  const f=fixture();await f.flush();
  f.snapshot.scores=[{school_room_id:7,aspect_id:3,score:4}];
  f.snapshot.notes=[{school_room_id:7,notes:'From teammate'}];
  f.snapshot.versions=[{school_room_id:7,field_key:'score:3',version:2},{school_room_id:7,field_key:'note',version:1},{school_room_id:7,field_key:'photo',version:3}];
  f.snapshot.presence=[{school_room_id:7,user_id:2,name:'Budi'}];
  await f.client.sync();
  assert(f.buttons[3].classList.contains('selected'));
  assert.equal(f.note.value,'From teammate');
  assert.match(f.presence.textContent,/Budi sedang mengisi/);
  assert.equal(f.client.photoVersion(7),3);
  assert(f.requests.every(r=>r.endpoint==='/state'));
});

test('stale field is not overwritten and requires an explicit conflict choice',async()=>{
  const f=fixture();await f.flush();
  f.snapshot.scores=[{school_room_id:7,aspect_id:3,score:5}];
  f.snapshot.versions=[{school_room_id:7,field_key:'score:3',version:1}];
  await assert.rejects(f.client.request('/score',{school_room_id:7,aspect_id:3,score:2}),/Conflict/);
  assert(f.client.hasUnsaved());
  const panel=f.issues.children.at(-1);
  assert.match(panel.children[1].textContent,/2/);
  assert.match(panel.children[2].textContent,/5/);
  panel.children[3].onclick(); // Explicitly use latest team value.
  assert(!f.client.hasUnsaved());
  assert(f.buttons[4].classList.contains('selected'));
});

test('successful requests send versions and unsaved network failures block final submit',async()=>{
  const f=fixture();await f.flush();
  await f.client.request('/score',{school_room_id:7,aspect_id:3,score:4});
  await f.flush();
  assert.equal(f.requests.find(r=>r.endpoint==='/score').data.base_version,0);
  f.setOffline(true);
  await assert.rejects(f.client.request('/note',{school_room_id:7,notes:'Keep local'}),/Offline/);
  let blocked=false;
  f.form.submit({preventDefault(){blocked=true},stopImmediatePropagation(){}});
  assert(blocked);
  assert(f.client.hasUnsaved());
});

test('team finalization locks edit controls and provides result link',async()=>{
  const f=fixture();await f.flush();
  f.snapshot.status='submitted';await f.client.sync();
  assert.equal(f.submitButton.disabled,true);
  assert.equal(f.resultLink.hidden,false);
  await assert.rejects(f.client.request('/note',{school_room_id:7,notes:'Too late'}),/sudah dikirim/);
});


test('a conflict in queued edits keeps the most recent local value available', async () => {
  const f=fixture();await f.flush();
  f.snapshot.scores=[{school_room_id:7,aspect_id:3,score:5}];
  f.snapshot.versions=[{school_room_id:7,field_key:'score:3',version:1}];
  const first=f.client.request('/score',{school_room_id:7,aspect_id:3,score:2});
  const second=f.client.request('/score',{school_room_id:7,aspect_id:3,score:3});
  await Promise.allSettled([first,second]);
  const panel=f.issues.children.at(-1);
  assert.match(panel.children[1].textContent,/3/);
  assert(f.client.hasUnsaved());
});
