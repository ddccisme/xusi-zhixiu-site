/**
 * 叙思织绣独立站 - 全局配置
 *
 * 通过环境变量或部署时修改此文件，可适配不同环境。
 * 生产环境建议通过反向代理将 API 与静态页面部署在同域，此时可将 API_BASE 设为空字符串或相对路径。
 */
const API_BASE = (function () {
  // 若页面通过 file:// 协议打开，回退到本地开发地址
  const isFileProtocol = window.location.protocol === 'file:';
  const localApi = 'http://127.0.0.1:8080/api';

  // 生产环境：如果 API 与页面同域，使用相对路径 '/api'
  // 开发环境：使用本地地址
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return isFileProtocol ? localApi : '/api';
  }

  // 其他域名默认使用同域 API，如需跨域请在此处修改
  return '/api';
})();
