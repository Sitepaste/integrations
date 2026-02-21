import { App, Modal, Setting } from 'obsidian';
import type { FilePublishInfo } from '../publish';
import { pagePath } from '../utils';

export class ConfirmModal extends Modal {
  private infos: FilePublishInfo[];
  private onConfirm: () => void;
  private onCancel: () => void;
  private confirmed = false;

  constructor(app: App, infos: FilePublishInfo[], onConfirm: () => void, onCancel: () => void) {
    super(app);
    this.infos = infos;
    this.onConfirm = onConfirm;
    this.onCancel = onCancel;
  }

  onOpen(): void {
    const { contentEl } = this;

    this.setTitle('Publish to Sitepaste');

    contentEl.createEl('p', {
      text: `This will publish ${this.infos.length} page${this.infos.length > 1 ? 's' : ''}.`,
    });

    const list = contentEl.createEl('ul');
    for (const info of this.infos) {
      list.createEl('li', {
        text: `${info.file.basename} → ${pagePath(info.contentType, info.slug, info.section)}`,
      });
    }

    new Setting(contentEl)
      .addButton((btn) => btn.setButtonText('Cancel').onClick(() => this.close()))
      .addButton((btn) =>
        btn
          .setButtonText('Publish')
          .setCta()
          .onClick(() => {
            this.confirmed = true;
            this.close();
            this.onConfirm();
          }),
      );
  }

  onClose(): void {
    this.contentEl.empty();
    if (!this.confirmed) {
      this.onCancel();
    }
  }
}
