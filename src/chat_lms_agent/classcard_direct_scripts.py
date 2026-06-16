READ_STUDY_DATA_SCRIPT = """
() => {
  const data = window.study_data || {};
  const candidates = [
    data.cards,
    data.card_list,
    data.cardList,
    window.cards,
    Array.isArray(data) ? data : null,
  ];
  const cards = candidates.find((item) => Array.isArray(item)) || [];
  return cards.map((card) => ({
    front: String(card.front || card.word || card.term || ''),
    back: String(card.back || card.meaning || card.definition || ''),
    audio_path: String(card.audio_path || card.audio || card.audioPath || ''),
  }));
}
"""


READ_CLASS_SETS_SCRIPT = """
({title, wordCount}) => {
  const normalizedTitle = String(title || '').replace(/\\s+/g, ' ').trim();
  const expectedCount = String(wordCount || '');
  const setIdFromHref = (href) => {
    const segments = String(href || '').split('/').filter(Boolean);
    if (segments[0] === 'Modal' && segments[1] === 'addSetFull' && segments.length >= 6) {
      const last = segments[segments.length - 1];
      return /^\\d+$/.test(last) ? last : '';
    }
    const setMatch = String(href || '').match(/\\/set\\/(\\d+)/i);
    return setMatch ? setMatch[1] : '';
  };
  const setItems = Array.from(document.querySelectorAll('[data-idx][data-cnt]'));
  const rows = setItems.map((item) => ({
    set_idx: String(item.dataset.idx || ''),
    text: [String(item.innerText || ''), String(item.dataset.cnt || '')].join(' '),
  }));
  const anchors = Array.from(document.querySelectorAll('a[href*="/Modal/addSetFull/"]'));
  const anchorRows = anchors.map((anchor) => {
    const href = anchor.getAttribute('href') || '';
    let node = anchor;
    let text = '';
    for (let depth = 0; depth < 8 && node; depth += 1) {
      text = String(node.innerText || '');
      const compact = text.replace(/\\s+/g, ' ').trim();
      if (compact.includes(normalizedTitle) && compact.includes(expectedCount)) break;
      node = node.parentElement;
    }
    return {set_idx: setIdFromHref(href), text};
  });
  return rows.concat(anchorRows);
}
"""


SUGGEST_AUDIO_SCRIPT = """
async ({rows}) => {
  const ajax = (opts) => new Promise((resolve) => {
    window.jQuery.ajax({...opts, success: resolve, error: (xhr, status, error) => {
      resolve({result: 'error', status, error, text: xhr.responseText?.slice(0, 500)});
    }});
  });
  const cards = [];
  for (let idx = 0; idx < rows.length; idx += 1) {
    const [front, back] = rows[idx];
    const response = await ajax({
      url: '/CreateWord/suggest',
      global: false,
      type: 'POST',
      dataType: 'json',
      data: {word: front, word_lang: 'en', is_word: 1, is_img: 0, set_type: 1, is_exam: 0},
    });
    if (response.result !== 'ok' || !response.msg) {
      return {stage: 'suggest', index: idx, front, response};
    }
    cards.push({front, back, audio_path: String(response.msg.audio_path || '')});
  }
  return {stage: 'completed', cards};
}
"""


DIRECT_UPLOAD_SCRIPT = """
async ({classIdx, rows, title}) => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const ajax = (opts) => new Promise((resolve) => {
    window.jQuery.ajax({...opts, success: resolve, error: (xhr, status, error) => {
      resolve({result: 'error', status, error, text: xhr.responseText?.slice(0, 500)});
    }});
  });
  const setValue = (selector, value) => {
    const el = document.querySelector(selector);
    if (el) el.value = value;
  };
  const suggestAudioPath = async (front) => {
    const response = await ajax({
      url: '/CreateWord/suggest',
      global: false,
      type: 'POST',
      dataType: 'json',
      data: {word: front, word_lang: 'en', is_word: 1, is_img: 0, set_type: 1, is_exam: 0},
    });
    if (response.result !== 'ok' || !response.msg) {
      return {ok: false, response};
    }
    return {ok: true, audio_path: String(response.msg.audio_path || '')};
  };
  setValue('#setForm #name', title);
  setValue('#modal_name', title);
  setValue('#setForm #front_lang', 'en');
  setValue('#setForm #back_lang', 'ko');
  setValue('#setForm #card_cnt', String(rows.length));
  const titleView = document.querySelector('.name-view');
  if (titleView) titleView.textContent = title;
  while (document.querySelectorAll('.input-row:not(.hidden)').length < rows.length) {
    const addButton = document.querySelector('.btn-bottom-add-card');
    if (!addButton) return {stage: 'rowSetup', response: 'add card button missing'};
    addButton.click();
    await sleep(50);
  }
  const visibleRows = Array.from(document.querySelectorAll('.input-row:not(.hidden)'));
  const expectedCards = [];
  for (let idx = 0; idx < rows.length; idx += 1) {
    const [front, back] = rows[idx];
    const row = visibleRows[idx];
    if (!row) return {stage: 'rowSetup', index: idx, response: 'visible row missing'};
    row.querySelector('textarea[name="front[]"]').value = front;
    row.querySelector('textarea[name="back[]"]').value = back;
    const suggested = await suggestAudioPath(front);
    if (!suggested.ok) return {stage: 'suggest', index: idx, front, response: suggested.response};
    const audio = row.querySelector('input[name="audio_path[]"]');
    if (!audio) return {stage: 'audioPath', index: idx, front, response: 'audio_path[] missing'};
    audio.value = suggested.audio_path;
    const cardOrder = row.querySelector('input[name="card_order[]"]');
    if (cardOrder) cardOrder.value = String(idx + 1);
    const deleted = row.querySelector('input[name="deleted[]"]');
    if (deleted) deleted.value = '0';
    expectedCards.push({front, back, audio_path: suggested.audio_path});
  }
  const saveSet = await ajax({url: '/CreateWord/saveSet', global: false, type: 'POST',
    data: window.jQuery('#setForm').serialize(), dataType: 'json'});
  if (saveSet.result !== 'ok') return {stage: 'saveSet', response: saveSet};
  const setIdx = String(saveSet.msg);
  setValue('#setForm #set_idx', setIdx);
  window.jQuery('[name="makeForm"]').find('#set_idx').val(setIdx);
  window.jQuery('[name="makeForm"]').find('[name="set_idx[]"]').remove();
  const makeForm = window.jQuery('[name="makeForm"]')[0];
  const dataObj = typeof window.formToJSON === 'function' ? window.formToJSON(makeForm) : '{}';
  const saveCard = await ajax({url: '/CreateWord/saveCard2', global: false, type: 'POST',
    data: {data_obj: dataObj}, dataType: 'json'});
  if (saveCard.result !== 'ok') return {stage: 'saveCard2', set_idx: setIdx, response: saveCard};
  const userIdx = document.querySelector('#setForm #login_user_idx')?.value || '';
  const add = await ajax({url: '/ViewSetAsync/addclass3', global: false, type: 'POST',
    data: {is_display: 1, set_idx: [setIdx], class_idxs: [classIdx], user_idx: userIdx}, dataType: 'json'});
  if (add.result !== 'ok') return {stage: 'addclass3', set_idx: setIdx, response: add};
  return {stage: 'completed', set_idx: setIdx, cards: expectedCards};
}
"""


REPAIR_AUDIO_SCRIPT = """
async ({setId}) => {
  const ajax = (opts) => new Promise((resolve) => {
    window.jQuery.ajax({...opts, success: resolve, error: (xhr, status, error) => {
      resolve({result: 'error', status, error, text: xhr.responseText?.slice(0, 500)});
    }});
  });
  const suggestAudioPath = async (front) => {
    const response = await ajax({
      url: '/CreateWord/suggest',
      global: false,
      type: 'POST',
      dataType: 'json',
      data: {word: front, word_lang: 'en', is_word: 1, is_img: 0, set_type: 1, is_exam: 0},
    });
    if (response.result !== 'ok' || !response.msg) {
      return {ok: false, response};
    }
    return {ok: true, audio_path: String(response.msg.audio_path || '')};
  };
  const rows = Array.from(document.querySelectorAll('.input-row:not(.hidden)'));
  const expectedCards = [];
  for (let idx = 0; idx < rows.length; idx += 1) {
    const row = rows[idx];
    const front = String(row.querySelector('textarea[name="front[]"]')?.value || '').trim();
    const back = String(row.querySelector('textarea[name="back[]"]')?.value || '').trim();
    if (!front || !back) return {stage: 'readRow', index: idx, response: 'blank front/back'};
    const suggested = await suggestAudioPath(front);
    if (!suggested.ok) return {stage: 'suggest', index: idx, front, response: suggested.response};
    const audio = row.querySelector('input[name="audio_path[]"]');
    if (!audio) return {stage: 'audioPath', index: idx, front, response: 'audio_path[] missing'};
    audio.value = suggested.audio_path;
    const deleted = row.querySelector('input[name="deleted[]"]');
    if (deleted) deleted.value = '0';
    const cardOrder = row.querySelector('input[name="card_order[]"]');
    if (cardOrder) cardOrder.value = String(idx + 1);
    expectedCards.push({front, back, audio_path: suggested.audio_path});
  }
  const setIdx = String(setId);
  const setIdxInput = document.querySelector('#setForm #set_idx');
  if (setIdxInput) setIdxInput.value = setIdx;
  const saveSet = await ajax({url: '/CreateWord/saveSet', global: false, type: 'POST',
    data: window.jQuery('#setForm').serialize(), dataType: 'json'});
  if (saveSet.result !== 'ok') return {stage: 'saveSet', set_idx: setIdx, response: saveSet};
  window.jQuery('[name="makeForm"]').find('#set_idx').val(setIdx);
  window.jQuery('[name="makeForm"]').find('[name="set_idx[]"]').remove();
  const makeForm = window.jQuery('[name="makeForm"]')[0];
  const dataObj = typeof window.formToJSON === 'function' ? window.formToJSON(makeForm) : '{}';
  const saveCard = await ajax({url: '/CreateWord/saveCard2', global: false, type: 'POST',
    data: {data_obj: dataObj}, dataType: 'json'});
  if (saveCard.result !== 'ok') return {stage: 'saveCard2', set_idx: setIdx, response: saveCard};
  return {stage: 'completed', set_idx: setIdx, cards: expectedCards};
}
"""
