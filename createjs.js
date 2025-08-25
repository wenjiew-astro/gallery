const fs = require('fs-extra');
const path = require('path');

// 兼容各种导出形式：function / { imageSize } / { default }
const imgMod = require('image-size');
const imageSize = typeof imgMod === 'function' ? imgMod : (imgMod.imageSize || imgMod.default);

const rootPath = 'gallery';   // 相册根目录（不用末尾斜杠）

class PhotoExtension {
  constructor() {
    this.size = 64;
    this.offset = [0, 0];
  }
}

class Photo {
  constructor() {
    this.dirName = '';
    this.fileName = '';
    this.iconID = '';
    this.extension = new PhotoExtension();
  }
}

class PhotoGroup {
  constructor() {
    this.name = '';
    this.children = [];
  }
}

const IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.svg']);

function createPlotIconsData() {
  let allPlots = [];
  let allPlotGroups = [];

  const plotJsonFile = path.join(__dirname, 'photosInfo.json');
  const plotGroupJsonFile = path.join(__dirname, 'photos.json');

  if (fs.existsSync(plotJsonFile)) {
    allPlots = JSON.parse(fs.readFileSync(plotJsonFile, 'utf8'));
  }
  if (fs.existsSync(plotGroupJsonFile)) {
    allPlotGroups = JSON.parse(fs.readFileSync(plotGroupJsonFile, 'utf8'));
  }

  // 只遍历相册根目录
  const rootDir = path.join(__dirname, rootPath);
  if (!fs.existsSync(rootDir)) {
    console.error(`根目录不存在：${rootDir}`);
    return;
  }

  fs.readdirSync(rootDir).forEach((dirName) => {
    const dirFull = path.join(rootDir, dirName);
    if (!fs.statSync(dirFull).isDirectory()) return;

    const subfiles = fs.readdirSync(dirFull);
    subfiles.forEach((subfileName) => {
      const ext = path.extname(subfileName).toLowerCase();
      if (!IMAGE_EXTS.has(ext)) return; // 只处理图片

      // 如果已存在可跳过（按需打开）
      // if (allPlots.find(o => o.fileName === subfileName && o.dirName === dirName)) return;

      const imgPath = path.join(dirFull, subfileName);

      try {
        const info = imageSize(imgPath); // 这里已兼容函数获取
        const plot = new Photo();
        plot.dirName = dirName;
        plot.fileName = subfileName;
        plot.iconID = `${info.width}.${info.height} ${subfileName}`;
        allPlots.push(plot);

        let group = allPlotGroups.find(o => o.name === dirName);
        if (!group) {
          group = new PhotoGroup();
          group.name = dirName;
          allPlotGroups.push(group);
        }
        group.children.push(plot.iconID);
        console.log('✔ 新增图片：', plot.iconID);
      } catch (e) {
        console.warn('⚠ 读取图片尺寸失败：', imgPath, e.message);
      }
    });
  });

  fs.writeJSONSync(plotJsonFile, allPlots, { spaces: 2 });
  fs.writeJSONSync(plotGroupJsonFile, allPlotGroups, { spaces: 2 });
}

createPlotIconsData();
