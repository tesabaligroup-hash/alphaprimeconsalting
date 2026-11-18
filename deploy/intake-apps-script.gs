/**
 * Alpha Prime — связь таблицы производства с приложением.
 * doPost — автозаявки (лист «Заявки авто» + папка клиента на Диске).
 * doGet  — приложение читает статусы услуг, партнёров и даты окончания виз.
 *          Логины и пароли из таблицы НЕ отдаются никогда.
 * Вставляется в САМУ таблицу производства: Расширения → Apps Script.
 * Заявки пишутся на отдельный лист «Заявки авто» (ваши листы не трогаются),
 * документы клиента — в папку на Google Диске.
 */
const SECRET = 'ВСТАВЬТЕ_СЕКРЕТ';          // тот же, что INTAKE_SCRIPT_SECRET на сервере
const ROOT_FOLDER_ID = ''; // можно оставить пустым — скрипт сам создаст на Диске папку «Клиенты Alpha Prime»
const SHEET_NAME = 'Заявки авто';
const VERSION = 5;  // проверка в браузере: ссылка …/exec?secret=…&action=version

function doPost(e) {
  try { return post_(e); } catch (err) { return out_({ ok: false, error: String(err) }); }  // всегда отвечаем JSON
}

function post_(e) {
  const d = JSON.parse(e.postData.contents);
  if (d.secret !== SECRET) return out_({ ok: false, error: 'неверный секрет' });
  let folder = null;
  if (d.folder_id) { try { folder = DriveApp.getFolderById(d.folder_id); } catch (err) { folder = null; } }  // папка клиента из Kommo
  if (!folder) {
    const root = root_();
    const found = root.getFoldersByName(d.folder_name);
    folder = found.hasNext() ? found.next() : root.createFolder(d.folder_name);
  }
  (d.files || []).forEach(function (f) {
    if (!folder.getFilesByName(f.name).hasNext()) {
      folder.createFile(Utilities.newBlob(Utilities.base64Decode(f.data), f.mime, f.name));
    }
  });
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.setFrozenRows(1);
  }
  // Колонки — как на листе «Производство» (строку можно скопировать туда целиком) + «ID сделки» + «Проверить»
  if (sh.getMaxColumns() < d.header.length) sh.insertColumnsAfter(sh.getMaxColumns(), d.header.length - sh.getMaxColumns());
  sh.getRange(1, 1, 1, d.header.length).setValues([d.header]).setFontWeight('bold').setBackground('#FBF7EC');
  const idCol = d.header.indexOf('ID сделки');
  const nameCol = d.header.indexOf('Клиент');
  const last = Math.max(sh.getLastRow(), 1);
  const have = sh.getRange(1, 1, last, d.header.length).getValues()
    .map(function (r) { return String(r[idCol]) + '|' + String(r[nameCol]); });
  (d.rows || [d.row]).forEach(function (r) {
    // текст, похожий на формулу (+7…, =…), пишем как текст
    const row = r.map(function (v) { v = v === '{folder}' ? folder.getUrl() : v; return (typeof v === 'string' && /^[=+\-@]/.test(v)) ? "'" + v : v; });
    const at = have.indexOf(String(row[idCol]) + '|' + String(row[nameCol]));
    if (at > 0) sh.getRange(at + 1, 1, 1, row.length).setValues([row]);
    else { sh.appendRow(row); have.push(String(row[idCol]) + '|' + String(row[nameCol])); }
  });
  return out_({ ok: true, folder_url: folder.getUrl() });
}

function root_() {
  if (ROOT_FOLDER_ID) return DriveApp.getFolderById(ROOT_FOLDER_ID);
  const it = DriveApp.getRootFolder().getFoldersByName('Клиенты Alpha Prime');
  return it.hasNext() ? it.next() : DriveApp.getRootFolder().createFolder('Клиенты Alpha Prime');
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ---------- чтение таблицы приложением (только нужные колонки) ----------
function doGet(e) {
  const p = e.parameter || {};
  if (p.secret !== SECRET) return out_({ ok: false, error: 'неверный секрет' });
  if (p.action === 'version') return out_({ ok: true, version: VERSION });
  // Документы клиентов с Диска (папка из поля «Документы» в Kommo)
  if (p.action === 'list') {
    try { return out_({ ok: true, files: list_(DriveApp.getFolderById(p.folder), '', 0) }); }
    catch (err) { return out_({ ok: false, error: 'нет доступа к папке: ' + err }); }
  }
  if (p.action === 'file') {
    try {
      const f = DriveApp.getFileById(p.id);
      if (f.getSize() > 15 * 1024 * 1024) return out_({ ok: false, error: 'файл больше 15 МБ' });
      return out_({ ok: true, name: f.getName(), mime: f.getMimeType(), modified: f.getLastUpdated().toISOString(),
                    data: Utilities.base64Encode(f.getBlob().getBytes()) });
    } catch (err) { return out_({ ok: false, error: 'нет доступа к файлу: ' + err }); }
  }
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return out_({
    ok: true,
    // Производство: №строки, C начало, D менеджер, E партнёр, G услуга, I контакты, N статус, O клиент, T цена, V оплатил, W долг, X доля партнёров, AA ID сделки
    production: cols_(ss.getSheetByName('Производство'), [3, 4, 5, 7, 9, 14, 15, 20, 22, 23, 24, 27], true),
    // Продления: A виза, B клиент, F статус, H дата окончания (колонки с логинами/паролями не читаются)
    renewals: cols_(ss.getSheetByName('Продления и доступы'), [1, 2, 6, 8], false)
      .concat(cols_(ss.getSheetByName('Новые продления'), [1, 2, 6, 8], false)),
    partners: cols_(ss.getSheetByName('Список партнеров'), [1, 2], false),
  });
}

function list_(folder, path, depth) {
  let res = [];
  const files = folder.getFiles();
  while (files.hasNext()) {
    const f = files.next();
    res.push({ id: f.getId(), name: f.getName(), mime: f.getMimeType(), size: f.getSize(),
               modified: f.getLastUpdated().toISOString(), path: path });
  }
  if (depth < 2) {
    const subs = folder.getFolders();
    while (subs.hasNext()) {
      const sub = subs.next();
      res = res.concat(list_(sub, path + sub.getName() + '/', depth + 1));
    }
  }
  return res;
}

function cols_(sh, cols, withRow) {
  if (!sh || sh.getLastRow() < 2) return [];
  const last = sh.getLastRow();
  const vals = sh.getRange(2, 1, last - 1, Math.max.apply(null, cols)).getDisplayValues();
  const res = [];
  vals.forEach(function (r, i) {
    const row = cols.map(function (c) { return r[c - 1]; });
    if (row.join('').trim() === '') return;
    res.push(withRow ? [i + 2].concat(row) : row);
  });
  return res;
}
