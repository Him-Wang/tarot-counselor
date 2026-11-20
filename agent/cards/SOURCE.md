# 牌面图片来源

`agent/cards/` 下的 78 张牌面，是韦特塔罗（Rider–Waite–Smith，1909 年，A. E. Waite 构想、
Pamela Colman Smith 绘制）**「Roses & Lilies」原版的公有领域扫描件**的 420px 缩图。

- 原始扫描来源：Wikimedia Commons 分类
  `Category:Rider-Waite_tarot_deck_(Roses_%26_Lilies)`
  <https://commons.wikimedia.org/wiki/Category:Rider-Waite_tarot_deck_(Roses_%26_Lilies)>
- 缩图取自开源项目 <https://github.com/hedanbaomi/tarot-divination-site> 的 `assets/cards/`
  目录，该项目说明这些是 Commons 公有领域文件的本地显示衍生件。

这些图像本身是公有领域的艺术作品。该开源项目的**软件代码**另行采用 AGPL-3.0 / MPL-2.0
授权，本项目**没有**使用其代码，只复制了这批公有领域图像文件，因此本项目的 MIT 授权不受影响。
若在司法辖区对 1909 年作品的版权状态有不同认定，请以当地法律与 Commons 各文件页为准。

本项目与牌作者、出版商及 Wikimedia Commons 均无关联，也未获其背书。

## 文件命名

- `major-00.jpeg` … `major-21.jpeg` —— 22 张大阿卡纳，按传统顺序（00 愚者 … 21 世界）
- `minor-<suit>-<rank>.jpeg` —— 56 张小阿卡纳
  - suit：`cups`（圣杯）/ `pentacles`（星币）/ `swords`（宝剑）/ `wands`（权杖）
  - rank：`ace` / `two` … `ten` / `page` / `knight` / `queen` / `king`

牌名 ↔ 文件名的映射在 `agent/tools.py` 的 `card_image()` 里，服务端通过 `/cards/<文件名>`
路由提供。
