import { Notice, Plugin, TFile, TFolder } from 'obsidian';
import { DEFAULT_SETTINGS, SitepasteSettingTab, type SitepasteSettings } from './settings';
import {
  prepareFile,
  doPublish,
  updateFrontmatter,
  collectMarkdownFiles,
  splitIntoBatches,
  type FilePublishInfo,
} from './publish';
import { DryRunModal } from './modals/dry-run';
import { ConfirmModal } from './modals/confirm';
import { ProgressModal } from './modals/progress';
import { ApiError, type PublishResponse } from './api';
import { pagePath } from './utils';

export default class SitepastePlugin extends Plugin {
  settings: SitepasteSettings = { ...DEFAULT_SETTINGS };
  private settingTab!: SitepasteSettingTab;
  private publishing = false;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.addRibbonIcon('upload', 'Publish to Sitepaste', () => {
      const file = this.app.workspace.getActiveFile();
      if (!file || file.extension !== 'md') {
        new Notice('Open a markdown file to publish.');
        return;
      }
      this.publishSingleFile(file).catch((e) => this.handleError(e));
    });

    this.addCommand({
      id: 'publish-current-file',
      name: 'Publish current file',
      checkCallback: (checking) => {
        const file = this.app.workspace.getActiveFile();
        if (!file || file.extension !== 'md') return false;
        if (!checking) this.publishSingleFile(file).catch((e) => this.handleError(e));
        return true;
      },
    });

    this.registerEvent(
      this.app.workspace.on('file-menu', (menu, abstractFile) => {
        if (abstractFile instanceof TFile && abstractFile.extension === 'md') {
          menu.addItem((item) => {
            item
              .setTitle('Publish to Sitepaste')
              .setIcon('upload')
              .onClick(() =>
                this.publishSingleFile(abstractFile).catch((e) => this.handleError(e)),
              );
          });
        } else if (abstractFile instanceof TFolder) {
          menu.addItem((item) => {
            item
              .setTitle('Publish folder to Sitepaste')
              .setIcon('upload')
              .onClick(() => this.publishFolder(abstractFile).catch((e) => this.handleError(e)));
          });
        }
      }),
    );

    this.settingTab = new SitepasteSettingTab(this.app, this);
    this.addSettingTab(this.settingTab);
  }

  onunload(): void {
    this.settingTab.destroy();
  }

  async onExternalSettingsChange(): Promise<void> {
    await this.loadSettings();
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  private async publishSingleFile(file: TFile): Promise<void> {
    if (this.publishing) return;
    if (!this.guardApiKey()) return;

    this.publishing = true;
    try {
      const info = await prepareFile(this.app, file, this.settings.contentType);

      if (this.settings.dryRun) {
        this.publishing = false;
        new DryRunModal(this.app, [info]).open();
        return;
      }

      if (info.errors.length > 0) {
        this.publishing = false;
        const msgs = info.errors.map((e) => `${e.field}: ${e.message}`).join('\n');
        new Notice(`Validation failed:\n${msgs}`, 8000);
        return;
      }

      new ConfirmModal(
        this.app,
        [info],
        () => this.doSinglePublish(info),
        () => {
          this.publishing = false;
        },
      ).open();
    } catch (err) {
      this.publishing = false;
      throw err;
    }
  }

  private async doSinglePublish(info: FilePublishInfo): Promise<void> {
    try {
      const result = await doPublish(this.settings, [info]);

      let frontmatterFailed = false;
      try {
        await updateFrontmatter(this.app, info.file, info.slug);
      } catch {
        frontmatterFailed = true;
      }

      const action = info.isUpdate ? 'Updated' : 'Published';
      let msg = `${action} "${info.title}" (${pagePath(info.contentType, info.slug)})`;
      if (frontmatterFailed) {
        msg += '\nWarning: could not update local frontmatter.';
      }
      if (result.build?.deployUrl) {
        msg += `\nDeployed to ${result.build.deployUrl}`;
      } else if (result.build?.error) {
        msg += `\nBuild skipped: ${result.build.message || result.build.error}`;
      }
      new Notice(msg, frontmatterFailed ? 8000 : 5000);
    } catch (err) {
      this.handleError(err);
    } finally {
      this.publishing = false;
    }
  }

  private async publishFolder(folder: TFolder): Promise<void> {
    if (this.publishing) return;
    if (!this.guardApiKey()) return;

    this.publishing = true;
    try {
      const files = collectMarkdownFiles(folder);
      if (files.length === 0) {
        this.publishing = false;
        new Notice('No markdown files found in this folder.');
        return;
      }

      if (files.length > 50) {
        new Notice(`Preparing ${files.length} files...`);
      }

      const infos: FilePublishInfo[] = [];
      for (const file of files) {
        infos.push(await prepareFile(this.app, file, this.settings.contentType));
      }

      if (this.settings.dryRun) {
        this.publishing = false;
        new DryRunModal(this.app, infos).open();
        return;
      }

      const withErrors = infos.filter((i) => i.errors.length > 0);
      if (withErrors.length > 0) {
        this.publishing = false;
        new DryRunModal(this.app, infos).open();
        return;
      }

      // homepage must be published individually not as part of a folder batch
      const homepageFiles = infos.filter((i) => i.contentType === 'homepage');
      if (homepageFiles.length > 0) {
        this.publishing = false;
        new Notice(
          `Homepage must be published individually: ${homepageFiles.map((f) => f.file.basename).join(', ')}`,
          8000,
        );
        return;
      }

      // Check duplicate slugs within the same content type
      const slugKeys = new Map<string, string>();
      for (const info of infos) {
        const key = `${info.contentType}:${info.slug}`;
        const existing = slugKeys.get(key);
        if (existing) {
          this.publishing = false;
          new Notice(
            `Duplicate slug "${info.slug}" (${info.contentType}) in ${existing} and ${info.file.basename}`,
            8000,
          );
          return;
        }
        slugKeys.set(key, info.file.basename);
      }

      new ConfirmModal(
        this.app,
        infos,
        () => this.doFolderPublish(infos),
        () => {
          this.publishing = false;
        },
      ).open();
    } catch (err) {
      this.publishing = false;
      throw err;
    }
  }

  private async doFolderPublish(infos: FilePublishInfo[]): Promise<void> {
    const modal = new ProgressModal(this.app, infos.length);
    modal.open();

    try {
      for (const info of infos) {
        modal.log(`${info.file.basename} → ${pagePath(info.contentType, info.slug)}`);
      }

      const batches = splitIntoBatches(infos);
      let publishedCount = 0;
      const failedIndices = new Set<number>();
      let lastResult: PublishResponse | undefined;
      let globalIdx = 0;

      for (let b = 0; b < batches.length; b++) {
        const batch = batches[b];
        const isLast = b === batches.length - 1;
        const batchLabel = batches.length > 1 ? ` (batch ${b + 1}/${batches.length})` : '';
        modal.setStatus(`Publishing ${batch.length} page(s)${batchLabel}...`);

        try {
          // Only build on the last batch if all previous batches succeeded
          const shouldBuild = isLast && this.settings.triggerBuild && failedIndices.size === 0;
          const result = await doPublish(this.settings, batch, shouldBuild);
          publishedCount += batch.length;
          lastResult = result;
        } catch (err) {
          for (let i = 0; i < batch.length; i++) {
            failedIndices.add(globalIdx + i);
          }
          if (err instanceof ApiError) {
            modal.log(`Batch ${b + 1} error (${err.status}): ${err.message}`);
            const rawPages = err.body['pages'];
            if (err.status === 400 && rawPages && typeof rawPages === 'object') {
              const pageErrors = rawPages as Record<string, Record<string, string>>;
              for (const [idx, fields] of Object.entries(pageErrors)) {
                const pi = parseInt(idx, 10);
                const name = pi < batch.length ? batch[pi].file.basename : `page ${idx}`;
                for (const [field, msg] of Object.entries(fields)) {
                  modal.log(`  ${name}: ${field} - ${msg}`);
                }
              }
            }
          } else {
            modal.log(`Batch ${b + 1} error: ${err instanceof Error ? err.message : String(err)}`);
          }
        }
        globalIdx += batch.length;
        modal.setProgress(globalIdx);
      }

      modal.setStatus('Updating local files...');
      let frontmatterFailures = 0;
      for (let i = 0; i < infos.length; i++) {
        if (failedIndices.has(i)) continue;
        try {
          await updateFrontmatter(this.app, infos[i].file, infos[i].slug);
        } catch {
          frontmatterFailures++;
          modal.log(`Warning: could not update frontmatter for ${infos[i].file.basename}`);
        }
      }

      let summary: string;
      if (failedIndices.size === 0) {
        summary = `Published ${infos.length} page(s) successfully.`;
      } else if (publishedCount === 0) {
        summary = `Publish failed. All ${infos.length} page(s) failed.`;
      } else {
        summary = `Published ${publishedCount} of ${infos.length} page(s). ${failedIndices.size} failed.`;
      }
      if (frontmatterFailures > 0) {
        summary += ` ${frontmatterFailures} file(s) could not be updated locally.`;
      }
      if (lastResult?.build?.deployUrl) {
        summary += ` Deployed to ${lastResult.build.deployUrl}`;
      } else if (lastResult?.build?.error) {
        summary += ` Build skipped: ${lastResult.build.message || lastResult.build.error}`;
        modal.log(`Build: ${lastResult.build.message || lastResult.build.error}`);
      } else if (failedIndices.size > 0 && this.settings.triggerBuild) {
        summary += ' Build skipped due to failures.';
      }
      modal.setComplete(summary);
    } catch (err) {
      modal.setComplete('Publish failed unexpectedly.');
      modal.log(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      this.publishing = false;
    }
  }

  private guardApiKey(): boolean {
    if (!this.settings.apiKey) {
      new Notice('Set your Sitepaste API key in Settings > Sitepaste.');
      return false;
    }
    return true;
  }

  private handleError(err: unknown): void {
    if (!(err instanceof ApiError)) {
      new Notice(`Publish failed: ${err instanceof Error ? err.message : String(err)}`, 8000);
      return;
    }
    switch (err.status) {
      case 401:
        new Notice('Invalid API key. Check your key in Settings > Sitepaste.', 8000);
        break;
      case 403:
        new Notice('API access requires a Pro plan. Upgrade at sitepaste.com.', 8000);
        break;
      case 402:
        new Notice(
          `Quota exceeded: ${err.message}. Check your plan limits at sitepaste.com.`,
          8000,
        );
        break;
      case 413:
        new Notice(
          'Request too large. Try publishing a smaller folder or fewer files at once.',
          8000,
        );
        break;
      case 429:
        new Notice('Rate limited. Wait a moment and try again.', 8000);
        break;
      default: {
        let msg = `Publish failed (${err.status}): ${err.message}`;
        const rawPages = err.body['pages'];
        if (err.status === 400 && rawPages && typeof rawPages === 'object') {
          const pageErrors = rawPages as Record<string, Record<string, string>>;
          for (const [, fields] of Object.entries(pageErrors)) {
            for (const [field, fieldMsg] of Object.entries(fields)) {
              msg += `\n${field}: ${fieldMsg}`;
            }
          }
        }
        new Notice(msg, 8000);
      }
    }
  }
}
