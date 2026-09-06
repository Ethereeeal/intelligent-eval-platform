// Run: node tests/frontend_eiu_gate.cjs (no browser/dependencies or database writes).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const context = vm.createContext({ console, window: {}, setTimeout, clearTimeout });
for (const file of ['01-data.js', '03-lib.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'front-end/js', file), 'utf8'), context);
}
async function run() {
  await vm.runInContext(`
    apiGet = async path => path === '/api/documents' ? [{document_id:1,file_name:'测试文档',parse_status:'completed'}]
      : path === '/api/eiu' ? {items:[
        {eiu_id:1,document_id:1,statement:'绿色',auto_disposition:'green',quality_policy_version:'v1',quality_checks:{fidelity:{status:'pass'},completeness:{status:'pass'},atomicity:{status:'pass'},testability:{status:'fail'}}},
        {eiu_id:2,document_id:1,statement:'黄色',auto_disposition:'yellow',quality_status:'verified'},
        {eiu_id:3,document_id:1,statement:'<script>危险</script>',auto_disposition:'red',is_questionable:false},
        {eiu_id:4,document_id:1,statement:'历史待复核',route_color:'red',quality_status:'needs_review'},
        {eiu_id:5,document_id:1,statement:'历史已验证',route_color:'yellow',quality_status:'verified'}
      ]} : [];
    loadData();
  `, context);
  const doc = JSON.parse(vm.runInContext('JSON.stringify(DOCS.doc1)', context));
  assert.deepEqual(doc.kp.map(k => k.routeColor), ['green','yellow','red','yellow','green']);
  assert.equal(doc.claimStats.candidate, 5);
  assert.equal(doc.claimStats.rejected, 1);
  assert.equal(doc.kp[0].qualityText, '3/3 通过');
  assert.ok(!doc.kp[0].qualityDetail.includes('可测试性'));
  const html = vm.runInContext('kpTableHTML(DOCS.doc1.kp)', context);
  assert.ok(!/P0|P1|P2|全部通过|kp-status-select/.test(html));
  assert.ok(html.includes('&lt;script&gt;危险&lt;/script&gt;'));
  assert.ok(html.includes('data-disposition="red" style="display:none" data-filtered="1"'));
  const red = html.split('data-disposition="red"')[1].split('class="kp-tr"')[0];
  assert.ok(red.includes('只读'));
  assert.ok(!red.includes('kp-delete'));
  assert.equal((html.match(/data-kp-filter=/g) || []).length, 3);
  const rows = ['green','yellow','red'].map(disposition => ({dataset:{disposition},style:{},textContent:disposition,querySelector:()=>({textContent:disposition})}));
  const empty = {}, note = {};
  context.fixture = {dataset:{},querySelectorAll:s=>s === '.kp-tr' ? rows : [],querySelector:s=>s === '[data-kp-empty]' ? empty : note};
  vm.runInContext('refreshPagers = () => {}; applyKpFilters(fixture)', context);
  assert.deepEqual(rows.map(r=>r.style.display), ['', 'none', 'none']);
  context.fixture.dataset.disposition='red';
  vm.runInContext('applyKpFilters(fixture)', context);
  assert.deepEqual(rows.map(r=>r.style.display), ['none', 'none', '']);
  context.fixture.dataset.search='green';
  vm.runInContext('applyKpFilters(fixture)', context);
  assert.ok(rows.every(r=>r.style.display === 'none'));
  assert.equal(empty.hidden, false);
  console.log('PASS: EIU mapping, three checks, archive, escaping, color/search intersection');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
