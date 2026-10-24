"use strict";
const money = (cents) => new Intl.NumberFormat('th-TH', {style:'currency', currency:'THB'}).format(cents / 100);
const toCents = value => Math.round(Number(value || 0) * 100);

const uploadForm = document.querySelector('#upload-form');
if (uploadForm) {
  const input = document.querySelector('#image');
  const zone = document.querySelector('#dropzone');
  let previewUrl;
  function preview() {
    const file = input.files[0];
    document.querySelector('#upload-error').textContent = '';
    if (!file) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 10 * 1024 * 1024) {
      document.querySelector('#upload-error').textContent = 'เลือกภาพ JPG/PNG ขนาดไม่เกิน 10 MB'; input.value = ''; return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    document.querySelector('#preview').src = previewUrl;
    document.querySelector('#file-name').textContent = file.name;
    document.querySelector('#selected-file').hidden = false;
  }
  input.addEventListener('change', preview);
  document.querySelector('#clear-file').addEventListener('click', () => input.click());
  ['dragover', 'dragenter'].forEach(event => zone.addEventListener(event, e => {e.preventDefault(); zone.classList.add('drag-over');}));
  ['dragleave', 'drop'].forEach(event => zone.addEventListener(event, e => {e.preventDefault(); zone.classList.remove('drag-over');}));
  zone.addEventListener('drop', e => {if (e.dataTransfer.files.length) {input.files = e.dataTransfer.files; preview();}});
  uploadForm.addEventListener('submit', () => {const button = document.querySelector('#analyze-button'); button.disabled = true; button.textContent = 'กำลังอัปโหลด…';});
  fetch('/health').then(r=>r.json()).then(data => {
    document.querySelector('#service-status').textContent = data.full_pipeline_ready ? '● OCR และ AI พร้อมอ่านใบเสร็จ' : data.ocr.ready ? '● OCR พร้อม · AI ยังไม่พร้อม คุณอ่าน OCR และกรอกข้อมูลเองได้' : 'OCR ยังไม่พร้อม กรุณาตรวจการติดตั้ง คุณยังกรอกข้อมูลเองได้';
  }).catch(()=> {document.querySelector('#service-status').textContent = 'ตรวจสถานะไม่ได้ กรุณาโหลดหน้าใหม่';});
}

const processing = document.querySelector('#processing');
if (processing) {
  async function poll() {
    try {
      const response = await fetch(processing.dataset.statusUrl);
      if (!response.ok) throw new Error();
      const result = await response.json();
      if (['review','confirmed'].includes(result.status)) {location.reload(); return;}
      document.querySelector('#processing-status').textContent = result.status === 'queued' ? 'อยู่ในคิว รอใบเสร็จก่อนหน้าวิเคราะห์เสร็จ' : 'กำลังอ่านภาพและวิเคราะห์ข้อมูล คุณกลับมาเปิดรายการนี้ภายหลังได้';
    } catch {document.querySelector('#processing-status').textContent = 'การเชื่อมต่อขาดช่วง กำลังลองใหม่…';}
    setTimeout(poll, 2000);
  }
  setTimeout(poll, 1200);
}

const reviewForm = document.querySelector('#review-form');
if (reviewForm) {
  const list = document.querySelector('#items-list');
  const error = document.querySelector('#save-error');
  const value = name => reviewForm.elements.namedItem(name).value;
  let lastDifference = null;
  function totals() {
    const sum = [...list.querySelectorAll('[data-field="line_total"]')].reduce((acc,el)=>acc+toCents(el.value),0) - toCents(value('discount'));
    const diff = toCents(value('receipt_total')) - sum;
    document.querySelector('#calculated-total').textContent = money(sum);
    document.querySelector('#mismatch-notice').hidden = diff === 0;
    document.querySelector('#difference-message').textContent = `ยอดบนใบเสร็จต่างจากผลรวม ${money(diff)} กรุณาตรวจรายการ ส่วนลด และค่าบริการ`;
    if (diff !== lastDifference) reviewForm.elements.namedItem('acknowledge_mismatch').checked = false;
    lastDifference = diff;
  }
  function addItem() {
    if (list.children.length >= 100) {error.textContent = 'รองรับไม่เกิน 100 รายการ'; return;}
    list.append(document.querySelector('#item-template').content.cloneNode(true));
    list.lastElementChild.querySelector('[data-field="quantity"]').value = '1';
    totals();
  }
  document.querySelector('#add-item').addEventListener('click', addItem);
  list.addEventListener('click', event => {if(event.target.closest('.remove-item')) {event.target.closest('.item-row').remove(); totals();}});
  reviewForm.addEventListener('input',totals);
  if (!list.children.length) addItem();
  totals();
  reviewForm.addEventListener('submit',async event => {
    event.preventDefault(); error.textContent = '';
    if (!list.children.length) {error.textContent = 'กรุณาเพิ่มสินค้าอย่างน้อย 1 รายการ'; return;}
    const data = {merchant:value('merchant'),date:value('date'),receipt_total:value('receipt_total'),discount:value('discount'),adjustment_note:value('adjustment_note'),acknowledge_mismatch:reviewForm.elements.namedItem('acknowledge_mismatch').checked,
      items:[...list.querySelectorAll('.item-row')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-field]')].map(el=>[el.dataset.field,el.value])))};
    const button = document.querySelector('#save-button'); button.disabled = true;
    try {
      const response = await fetch(reviewForm.dataset.confirmUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(data)});
      const result = await response.json();
      if (!response.ok) {error.textContent = result.error || 'บันทึกไม่สำเร็จ กรุณาลองใหม่'; button.disabled = false; return;}
      location.assign(result.url);
    } catch {error.textContent = 'เชื่อมต่อไม่ได้ ข้อมูลที่กรอกยังอยู่ กรุณาลองบันทึกอีกครั้ง'; button.disabled = false;}
  });
}
