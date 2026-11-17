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
const ROOT_FOLDER_ID = 'ВСТАВЬТЕ_ID_ПАПКИ'; // папка «Клиенты» на Диске: id — часть ссылки после /folders/
const SHEET_NAME = 'Заявки авто';

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  if (d.secret !== SECRET) return out_({ ok: false, error: 'неверный секрет' });
  const root = DriveApp.getFolderById(ROOT_FOLDER_ID);
  const found = root.getFoldersByName(d.folder_name);
  const folder = found.hasNext() ? found.next() : root.createFolder(d.folder_name);
  (d.files || []).forEach(function (f) {
    if (!folder.getFilesByName(f.name).hasNext()) {
      folder.createFile(Utilities.newBlob(Utilities.base64Decode(f.data), f.mime, f.name));
    }
  });
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.appendRow(d.header);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, d.header.length).setFontWeight('bold').setBackground('#FBF7EC');
  }
  const row = d.row.map(function (v) { return v === '{folder}' ? folder.getUrl() : v; });
  const ids = sh.getRange(1, 1, Math.max(sh.getLastRow(), 1), 1).getValues().map(function (r) { return String(r[0]); });
  const at = ids.indexOf(String(row[0]));
  if (at > 0) sh.getRange(at + 1, 1, 1, row.length).setValues([row]);
  else sh.appendRow(row);
  return out_({ ok: true, folder_url: folder.getUrl() });
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ---------- чтение таблицы приложением (только нужные колонки) ----------
function doGet(e) {
  if ((e.parameter || {}).secret !== SECRET) return out_({ ok: false, error: 'неверный секрет' });
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return out_({
    ok: true,
    // Производство: №строки, C начало, D менеджер, E партнёр, G услуга, I контакты, N статус, O клиент, T цена, V оплатил, W долг, X доля партнёров
    production: cols_(ss.getSheetByName('Производство'), [3, 4, 5, 7, 9, 14, 15, 20, 22, 23, 24], true),
    // Продления: A виза, B клиент, F статус, H дата окончания (колонки с логинами/паролями не читаются)
    renewals: cols_(ss.getSheetByName('Продления и доступы'), [1, 2, 6, 8], false)
      .concat(cols_(ss.getSheetByName('Новые продления'), [1, 2, 6, 8], false)),
    partners: cols_(ss.getSheetByName('Список партнеров'), [1, 2], false),
  });
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
