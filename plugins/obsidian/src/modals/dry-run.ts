import { App, Modal } from 'obsidian';
import type { FilePublishInfo } from '../publish';

export class DryRunModal extends Modal {
  private infos: FilePublishInfo[];

  constructor(app: App, infos: FilePublishInfo[]) {
    super(app);
    this.infos = infos;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.addClass('sitepaste-dry-run');

    this.setTitle('Dry run summary');

    const table = contentEl.createEl('table', {
      cls: 'sitepaste-dry-run-table',
    });
    const thead = table.createEl('thead');
    const headerRow = thead.createEl('tr');
    for (const col of ['File', 'Slug', 'Type', 'Action', 'Status']) {
      headerRow.createEl('th', { text: col });
    }

    const tbody = table.createEl('tbody');
    let validCount = 0;
    let errorCount = 0;

    for (const info of this.infos) {
      const row = tbody.createEl('tr');
      row.createEl('td', { text: info.file.basename });
      row.createEl('td', { text: info.slug });
      row.createEl('td', { text: info.contentType });
      row.createEl('td', { text: info.isUpdate ? 'Update' : 'Create' });

      const statusCell = row.createEl('td');
      if (info.errors.length > 0) {
        errorCount++;
        statusCell.addClass('sitepaste-status-error');
        for (const err of info.errors) {
          statusCell.createEl('div', { text: `${err.field}: ${err.message}` });
        }
      } else {
        validCount++;
        statusCell.addClass('sitepaste-status-valid');
        statusCell.setText('Valid');
      }
    }

    const summary = contentEl.createEl('p', {
      cls: 'sitepaste-dry-run-summary',
    });
    summary.setText(`${this.infos.length} file(s): ${validCount} valid, ${errorCount} with errors`);
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
