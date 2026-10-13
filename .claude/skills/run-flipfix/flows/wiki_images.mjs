// Flow: inline images in Docs (wiki).
// Paste, "Add image" picker, drag-and-drop, and a rejected file on a new doc A;
// doc B reuses A's first image; delete A; age images and run the real orphan
// sweep; B must still show its image.
//
//   node .claude/skills/run-flipfix/driver.mjs flow .claude/skills/run-flipfix/flows/wiki_images.mjs
//
// Needs a fresh DB (start.sh --fresh): it creates docs titled "Doc A" / "Doc B".
// Leaves uploaded files in the repo's media/wiki/ - delete that dir afterwards.
// Expect one console error: the 400 from the deliberately rejected upload.

const IMAGE_REFS = /\/wiki\/media\/(\d+)\//g;
const countRefs = (sel, n) =>
  `(document.querySelector('${sel}').value.match(/\\/wiki\\/media\\/\\d+\\//g) || []).length === ${n}`;

export default async function ({ page, base, shot, manage }) {
  await page.goto(`${base}/wiki/create/`);
  await page.fill('#id_title', 'Doc A');
  const ta = page.locator('#id_content');
  await ta.fill('Intro paragraph');
  await ta.focus();
  await page.keyboard.press('End');

  // 1) Paste: a real ClipboardEvent carrying a canvas-generated PNG.
  await page.evaluate(async () => {
    const c = Object.assign(document.createElement('canvas'), { width: 400, height: 300 });
    const g = c.getContext('2d');
    g.fillStyle = '#36c';
    g.fillRect(0, 0, 400, 300);
    const blob = await new Promise((r) => c.toBlob(r, 'image/png'));
    const dt = new DataTransfer();
    dt.items.add(new File([blob], 'image.png', { type: 'image/png' }));
    document
      .querySelector('#id_content')
      .dispatchEvent(
        new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })
      );
  });
  const placeholder = await ta.inputValue();
  await page.waitForFunction(countRefs('#id_content', 1));
  const altSelected = await page.evaluate(() => {
    const t = document.querySelector('#id_content');
    return t.value.substring(t.selectionStart, t.selectionEnd);
  });
  await page.keyboard.type('Blue test panel');

  // 2) "Add image" button -> file chooser.
  const jpeg = await page.evaluate(async () => {
    const c = Object.assign(document.createElement('canvas'), { width: 1600, height: 900 });
    const g = c.getContext('2d');
    g.fillStyle = '#2a6';
    g.fillRect(0, 0, 1600, 900);
    return c.toDataURL('image/jpeg').split(',')[1];
  });
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.click('[data-image-upload-button]'),
  ]);
  await chooser.setFiles({
    name: 'belt_drive.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from(jpeg, 'base64'),
  });
  await page.waitForFunction(countRefs('#id_content', 2));

  // 3) Drag-and-drop: dragover + drop DragEvents with a DataTransfer.
  await page.evaluate(async () => {
    const c = Object.assign(document.createElement('canvas'), { width: 640, height: 480 });
    const g = c.getContext('2d');
    g.fillStyle = '#a26';
    g.fillRect(0, 0, 640, 480);
    const blob = await new Promise((r) => c.toBlob(r, 'image/png'));
    const dt = new DataTransfer();
    dt.items.add(new File([blob], 'left_flipper-coil.png', { type: 'image/png' }));
    const t = document.querySelector('#id_content');
    t.dispatchEvent(
      new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true })
    );
    t.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  });
  await page.waitForFunction(countRefs('#id_content', 3));

  // 4) A non-image chosen in the picker -> error toast, no leftover placeholder.
  const [chooser2] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.click('[data-image-upload-button]'),
  ]);
  await chooser2.setFiles({ name: 'mystery', mimeType: '', buffer: Buffer.from('not an image') });
  await page.waitForSelector('.message--error');
  const errorToast = await page.textContent('.message--error');
  const contentA = await ta.inputValue();
  await shot('wiki_images_1_editor');

  await page.click('button[type=submit]:has-text("Create Doc")');
  await page.waitForLoadState('networkidle');
  const imagesA = await page.$$eval('.markdown-content img', (els) =>
    els.map((e) => ({ src: e.getAttribute('src'), alt: e.alt, naturalWidth: e.naturalWidth }))
  );
  await shot('wiki_images_2_docA');

  // Doc B reuses A's first image.
  const sharedId = [...contentA.matchAll(IMAGE_REFS)][0][1];
  await page.goto(`${base}/wiki/create/`);
  await page.fill('#id_title', 'Doc B');
  await page.fill(
    '#id_content',
    `Uses the panel from Doc A\n\n![Blue test panel](/wiki/media/${sharedId}/)`
  );
  await page.click('button[type=submit]:has-text("Create Doc")');
  await page.waitForLoadState('networkidle');

  // Delete A, then age every image past the grace period and run the scheduled task.
  await page.goto(`${base}/wiki/delete/doc-a`);
  await page.click('button.btn--danger');
  await page.waitForLoadState('networkidle');
  const sweep = manage(
    'shell',
    '--no-imports',
    '-c',
    `
from datetime import timedelta
from django.utils import timezone
from flipfix.apps.wiki.models import WikiMedia
from flipfix.apps.wiki.tasks import delete_orphaned_wiki_media
WikiMedia.objects.update(created_at=timezone.now() - timedelta(days=30))
print('DELETED', delete_orphaned_wiki_media())
print('REMAINING', list(WikiMedia.objects.values_list('pk', flat=True)))
`
  )
    .split('\n')
    .filter((l) => /^(DELETED|REMAINING)/.test(l));

  await page.goto(`${base}/doc/doc-b`);
  await page.waitForLoadState('networkidle');
  const imagesB = await page.$$eval('.markdown-content img', (els) =>
    els.map((e) => ({ src: e.getAttribute('src'), naturalWidth: e.naturalWidth }))
  );
  await shot('wiki_images_3_docB_after_sweep');

  const ok =
    placeholder.includes('Uploading image.png') &&
    altSelected === 'image' &&
    imagesA.length === 3 &&
    imagesA.every((i) => i.naturalWidth > 0) &&
    imagesB.length === 1 &&
    imagesB[0].naturalWidth > 0 &&
    sweep.includes(`REMAINING [${sharedId}]`);
  if (!ok)
    throw new Error(
      `wiki image flow failed: ${JSON.stringify({ contentA, imagesA, sweep, imagesB })}`
    );
  return { ok, errorToast, contentA, imagesA, sweep, imagesB };
}
