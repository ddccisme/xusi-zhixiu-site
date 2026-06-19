/**
 * 多语言切换模块
 * 支持中文（zh）和英文（en）
 * 用法：
 * 1. 在 HTML 元素上添加 data-i18n="key"
 * 2. 在 assets/locales/{lang}.json 中定义翻译
 * 3. 调用 i18n.setLang('en') 切换语言
 */

const I18N = {
  currentLang: 'zh',
  translations: {},

  async init(defaultLang) {
    const saved = localStorage.getItem('xusi_lang');
    this.currentLang = saved || defaultLang || 'zh';
    await this.loadLang(this.currentLang);
    this.apply();
    this.updateToggleUI();
  },

  async loadLang(lang) {
    try {
      const res = await fetch(`./assets/locales/${lang}.json`);
      if (!res.ok) throw new Error(`load ${lang} failed`);
      this.translations = await res.json();
      this.currentLang = lang;
      localStorage.setItem('xusi_lang', lang);
      document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    } catch (e) {
      console.error('i18n load error:', e);
      this.translations = {};
    }
  },

  get(key, fallback) {
    const keys = key.split('.');
    let value = this.translations;
    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        return fallback !== undefined ? fallback : key;
      }
    }
    return typeof value === 'string' ? value : (fallback !== undefined ? fallback : key);
  },

  apply() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) {
        el.textContent = this.get(key);
      }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) {
        el.placeholder = this.get(key);
      }
    });

    document.querySelectorAll('[data-i18n-alt]').forEach(el => {
      const key = el.getAttribute('data-i18n-alt');
      if (key) {
        el.alt = this.get(key);
      }
    });

    this.updateToggleUI();

    // 触发自定义事件，便于页面做额外更新
    document.dispatchEvent(new CustomEvent('i18n:applied', { detail: { lang: this.currentLang } }));
  },

  async setLang(lang) {
    if (lang === this.currentLang) return;
    await this.loadLang(lang);
    this.apply();
  },

  toggle() {
    const next = this.currentLang === 'zh' ? 'en' : 'zh';
    this.setLang(next);
  },

  updateToggleUI() {
    document.querySelectorAll('[data-i18n-toggle]').forEach(el => {
      el.textContent = this.currentLang === 'zh' ? 'EN' : '中';
      el.setAttribute('title', this.currentLang === 'zh' ? 'Switch to English' : '切换到中文');
    });
  }
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
  I18N.init('zh');

  document.querySelectorAll('[data-i18n-toggle]').forEach(el => {
    el.addEventListener('click', () => I18N.toggle());
  });
});
