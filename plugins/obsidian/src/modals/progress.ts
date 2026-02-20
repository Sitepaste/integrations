import { App, Modal, Setting } from 'obsidian';

export class ProgressModal extends Modal {
  private progressBarFill!: HTMLElement;
  private statusText!: HTMLElement;
  private logContainer!: HTMLElement;
  private total: number;

  constructor(app: App, total: number) {
    super(app);
    this.total = total;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.addClass('sitepaste-progress');

    this.setTitle('Publishing to Sitepaste');

    this.statusText = contentEl.createEl('p', {
      cls: 'sitepaste-progress-status',
    });
    this.statusText.setText('Preparing...');

    const barContainer = contentEl.createEl('div', {
      cls: 'sitepaste-progress-bar',
    });
    this.progressBarFill = barContainer.createEl('div', {
      cls: 'sitepaste-progress-bar-fill',
    });

    this.logContainer = contentEl.createEl('div', {
      cls: 'sitepaste-progress-log',
    });
  }

  setStatus(message: string): void {
    this.statusText.setText(message);
  }

  setProgress(current: number): void {
    const pct = Math.round((current / this.total) * 100);
    this.progressBarFill.style.width = `${pct}%`;
  }

  log(message: string): void {
    this.logContainer.createEl('div', { text: message });
    this.logContainer.scrollTop = this.logContainer.scrollHeight;
  }

  setComplete(summary: string): void {
    this.progressBarFill.style.width = '100%';
    this.statusText.setText(summary);

    new Setting(this.contentEl).addButton((btn) =>
      btn
        .setButtonText('Close')
        .setCta()
        .onClick(() => this.close()),
    );
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
