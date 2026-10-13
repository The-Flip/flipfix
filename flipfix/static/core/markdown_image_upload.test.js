import { describe, it, expect } from 'vitest';
const {
  makePlaceholder,
  insertPlaceholder,
  replacePlaceholder,
  removePlaceholder,
  imageFiles,
} = require('./markdown_image_upload.js');

/** Apply a replacement descriptor to a string (what applyTextareaEdit does to .value). */
function apply(value, result) {
  return (
    value.substring(0, result.replaceStart) +
    result.replacement +
    value.substring(result.replaceEnd)
  );
}

const PH = makePlaceholder('photo.jpg', 'abc');
const MD = '![photo](/wiki/media/42/)';

describe('makePlaceholder', () => {
  it('includes the file name and token', () => {
    expect(PH).toBe('![Uploading photo.jpg…](uploading-abc)');
  });

  it('strips brackets that would break the markdown', () => {
    expect(makePlaceholder('a[1].png', 't')).toBe('![Uploading a1.png…](uploading-t)');
  });
});

describe('insertPlaceholder', () => {
  it('uses an empty textarea as-is', () => {
    const result = insertPlaceholder('', 0, PH);
    expect(apply('', result)).toBe(PH);
    expect(result.selectionStart).toBe(PH.length);
  });

  it('uses an empty first line as-is', () => {
    const value = '\nrest';
    expect(apply(value, insertPlaceholder(value, 0, PH))).toBe(`${PH}\nrest`);
  });

  it('goes on a new line after the current line, without splitting it', () => {
    const value = 'before after\nnext line';
    const result = insertPlaceholder(value, 6, PH);
    expect(apply(value, result)).toBe(`before after\n${PH}\nnext line`);
    expect(result.selectionStart).toBe('before after\n'.length + PH.length);
    expect(result.selectionEnd).toBe(result.selectionStart);
  });

  it('uses the current line when it is empty', () => {
    const value = 'intro\n\noutro';
    const result = insertPlaceholder(value, 6, PH);
    expect(apply(value, result)).toBe(`intro\n${PH}\noutro`);
  });

  it('never lands inside the previous image when its alt text is selected', () => {
    const value = `intro\n${MD}`;
    // the selection ends at the end of the selected alt text "photo"
    const result = insertPlaceholder(value, 'intro\n![photo'.length, PH);
    expect(apply(value, result)).toBe(`intro\n${MD}\n${PH}`);
  });
});

describe('replacePlaceholder', () => {
  it('selects the alt text when the cursor is still after the placeholder', () => {
    const value = `Intro\n${PH}`;
    const end = value.length;
    const result = replacePlaceholder(value, PH, MD, end, end);
    const updated = apply(value, result);
    expect(updated).toBe(`Intro\n${MD}`);
    expect(updated.substring(result.selectionStart, result.selectionEnd)).toBe('photo');
  });

  it('keeps the cursor when the author kept typing after the placeholder', () => {
    const value = `${PH}\nmore text`;
    const end = value.length;
    const result = replacePlaceholder(value, PH, MD, end, end);
    const updated = apply(value, result);
    expect(updated).toBe(`${MD}\nmore text`);
    expect(result.selectionStart).toBe(updated.length);
    expect(result.selectionEnd).toBe(updated.length);
  });

  it('leaves a cursor before the placeholder alone', () => {
    const value = `start ${PH}`;
    const result = replacePlaceholder(value, PH, MD, 2, 2);
    expect(result.selectionStart).toBe(2);
    expect(result.selectionEnd).toBe(2);
  });

  it('finds the placeholder by token after text was edited around it', () => {
    const other = makePlaceholder('other.jpg', 'xyz');
    const value = `typed while waiting\n${other}\n${PH}\nand after`;
    const result = replacePlaceholder(value, PH, MD, 0, 0);
    expect(apply(value, result)).toBe(`typed while waiting\n${other}\n${MD}\nand after`);
  });

  it('returns null when the author deleted the placeholder', () => {
    expect(replacePlaceholder('nothing here', PH, MD, 0, 0)).toBeNull();
  });
});

describe('removePlaceholder', () => {
  it('removes the placeholder with the newline inserted before it', () => {
    const inserted = `\n${PH}`;
    const value = `intro${inserted}`;
    const result = removePlaceholder(value, inserted, value.length, value.length);
    expect(apply(value, result)).toBe('intro');
    expect(result.selectionStart).toBe(5);
  });

  it('removes the placeholder and shifts a later cursor back', () => {
    const value = `a ${PH} b`;
    const end = value.length;
    const result = removePlaceholder(value, PH, end, end);
    expect(apply(value, result)).toBe('a  b');
    expect(result.selectionStart).toBe(4);
  });

  it('returns null when the placeholder is gone', () => {
    expect(removePlaceholder('text', PH, 0, 0)).toBeNull();
  });
});

describe('imageFiles', () => {
  it('keeps images and files with no MIME type, drops others', () => {
    const files = [
      { name: 'a.png', type: 'image/png' },
      { name: 'b.heic', type: '' },
      { name: 'c.txt', type: 'text/plain' },
      { name: 'd.mp4', type: 'video/mp4' },
    ];
    expect(imageFiles(files).map((f) => f.name)).toEqual(['a.png', 'b.heic']);
  });

  it('handles a missing file list', () => {
    expect(imageFiles(undefined)).toEqual([]);
  });
});
