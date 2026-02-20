import { App, PluginSettingTab, Setting } from 'obsidian';
import type SitepastePlugin from './main';

export interface SitepasteSettings {
  apiKey: string;
  siteId: string;
  contentType: string;
  triggerBuild: boolean;
  dryRun: boolean;
}

export const DEFAULT_SETTINGS: SitepasteSettings = {
  apiKey: '',
  siteId: '',
  contentType: 'docs',
  triggerBuild: true,
  dryRun: false,
};

export class SitepasteSettingTab extends PluginSettingTab {
  plugin: SitepastePlugin;
  private saveTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(app: App, plugin: SitepastePlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName('API key')
      .setDesc('Your Sitepaste API key. Found in Dashboard > Tokens.')
      .addText((text) => {
        text.inputEl.type = 'password';
        text
          .setPlaceholder('sp_...')
          .setValue(this.plugin.settings.apiKey)
          .onChange((value) => {
            this.plugin.settings.apiKey = value.trim();
            this.debounceSave();
          });
      });

    new Setting(containerEl)
      .setName('Site ID')
      .setDesc('Optional. Leave empty to use your default site.')
      .addText((text) =>
        text
          .setPlaceholder('abcd1234-5678-...')
          .setValue(this.plugin.settings.siteId)
          .onChange((value) => {
            this.plugin.settings.siteId = value.trim();
            this.debounceSave();
          }),
      );

    new Setting(containerEl)
      .setName('Default content type')
      .setDesc('Content type for pages without a contentType in frontmatter.')
      .addDropdown((dropdown) =>
        dropdown
          .addOptions({ docs: 'Docs', blog: 'Blog', standalone: 'Standalone' })
          .setValue(this.plugin.settings.contentType)
          .onChange((value) => {
            this.plugin.settings.contentType = value;
            this.flushSave();
          }),
      );

    new Setting(containerEl)
      .setName('Trigger build')
      .setDesc('Trigger a site build after publishing. Disable to save build quota.')
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.triggerBuild).onChange((value) => {
          this.plugin.settings.triggerBuild = value;
          this.flushSave();
        }),
      );

    new Setting(containerEl)
      .setName('Dry run')
      .setDesc(
        'When enabled, publish actions validate locally and show a summary without calling the API.',
      )
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.dryRun).onChange((value) => {
          this.plugin.settings.dryRun = value;
          this.flushSave();
        }),
      );
  }

  hide(): void {
    this.flushSave();
  }

  destroy(): void {
    this.flushSave();
  }

  private debounceSave(): void {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      this.plugin.saveSettings();
    }, 500);
  }

  private flushSave(): void {
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    this.plugin.saveSettings();
  }
}
