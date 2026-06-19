/* 叙思织绣 - 独立站脚本 */

document.addEventListener('DOMContentLoaded', function() {
  // 导航滚动效果
  const header = document.getElementById('header');
  window.addEventListener('scroll', function() {
    if (window.scrollY > 50) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  });

  // 移动端菜单
  const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
  const mobileMenu = document.getElementById('mobileMenu');
  mobileMenuBtn.addEventListener('click', function() {
    mobileMenu.classList.toggle('open');
    const spans = mobileMenuBtn.querySelectorAll('span');
    if (mobileMenu.classList.contains('open')) {
      spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
      spans[1].style.opacity = '0';
      spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
    } else {
      spans[0].style.transform = 'none';
      spans[1].style.opacity = '1';
      spans[2].style.transform = 'none';
    }
  });

  mobileMenu.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      mobileMenu.classList.remove('open');
      const spans = mobileMenuBtn.querySelectorAll('span');
      spans[0].style.transform = 'none';
      spans[1].style.opacity = '1';
      spans[2].style.transform = 'none';
    });
  });

  // 导航高亮
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.main-nav a');
  
  function highlightNav() {
    const scrollY = window.scrollY + 100;
    sections.forEach(section => {
      const sectionTop = section.offsetTop;
      const sectionHeight = section.offsetHeight;
      const sectionId = section.getAttribute('id');
      if (scrollY >= sectionTop && scrollY < sectionTop + sectionHeight) {
        navLinks.forEach(link => {
          link.classList.remove('active');
          if (link.getAttribute('href') === '#' + sectionId) {
            link.classList.add('active');
          }
        });
      }
    });
  }

  window.addEventListener('scroll', highlightNav);

  // 首页轮播
  const carouselTrack = document.querySelector('.carousel-track');
  const slides = document.querySelectorAll('.carousel-slide');
  const dots = document.querySelectorAll('.dot');
  const prevBtn = document.querySelector('.carousel-prev');
  const nextBtn = document.querySelector('.carousel-next');
  let currentSlide = 0;
  let slideInterval;

  function showSlide(index) {
    slides.forEach((slide, i) => {
      slide.classList.remove('active');
      dots[i].classList.remove('active');
    });
    slides[index].classList.add('active');
    dots[index].classList.add('active');
    currentSlide = index;
  }

  function nextSlide() {
    const next = (currentSlide + 1) % slides.length;
    showSlide(next);
  }

  function prevSlide() {
    const prev = (currentSlide - 1 + slides.length) % slides.length;
    showSlide(prev);
  }

  function startAutoPlay() {
    slideInterval = setInterval(nextSlide, 5000);
  }

  function stopAutoPlay() {
    clearInterval(slideInterval);
  }

  if (prevBtn && nextBtn) {
    prevBtn.addEventListener('click', () => {
      prevSlide();
      stopAutoPlay();
      startAutoPlay();
    });
    nextBtn.addEventListener('click', () => {
      nextSlide();
      stopAutoPlay();
      startAutoPlay();
    });
  }

  dots.forEach((dot, index) => {
    dot.addEventListener('click', () => {
      showSlide(index);
      stopAutoPlay();
      startAutoPlay();
    });
  });

  if (slides.length > 0) startAutoPlay();

  // 自营产品筛选
  const filterBtns = document.querySelectorAll('.filter-btn');
  const productCards = document.querySelectorAll('.product-card');

  filterBtns.forEach(btn => {
    btn.addEventListener('click', function() {
      filterBtns.forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      const filter = this.dataset.filter;

      productCards.forEach(card => {
        if (filter === 'all' || card.dataset.category === filter) {
          card.classList.remove('hidden');
          card.style.animation = 'fadeIn 0.5s ease';
        } else {
          card.classList.add('hidden');
        }
      });
    });
  });

  // 自营产品卡片点击跳转详情页
  productCards.forEach(card => {
    const detailUrl = card.dataset.detail;
    if (detailUrl) {
      card.addEventListener('click', function(e) {
        if (e.target.closest('.btn-inquiry')) return;
        window.location.href = detailUrl;
      });
    }
  });

  // 文物展示筛选（联动：来源 → 类型 → 年代）
  const relicItems = document.querySelectorAll('.relic-item');
  const sourceFilterGroup = document.getElementById('sourceFilterGroup');
  const typeFilterGroup = document.getElementById('typeFilterGroup');
  const eraFilterGroup = document.getElementById('eraFilterGroup');

  // 参考中国丝绸博物馆藏品分类
  const relicFiltersConfig = {
    all: {
      types: ['全部'],
      eras: ['全部']
    },
    ancient: {
      label: '中国历代',
      types: ['全部', '织物', '服装', '工艺品', '其他'],
      eras: ['全部', '战国', '汉晋', '南北朝', '隋唐', '宋代', '辽代', '元代', '明代', '清代', '民国', '现代']
    },
    contemporary: {
      label: '中国当代',
      types: ['全部', '大师服装', '新秀服装', '品牌服饰', '面料', '家纺', '图案手稿', '其他'],
      eras: ['全部', '当代']
    },
    western: {
      label: '西方',
      types: ['全部', '织物', '服装', '配饰', '家纺', '其他'],
      eras: ['全部', '10—15世纪', '16世纪', '17世纪', '18世纪', '19世纪', '20世纪', '21世纪']
    },
    ethnology: {
      label: '民族学',
      types: ['全部', '织物', '服装', '配饰', '家纺', '其他'],
      eras: ['全部', '战国', '汉晋', '南北朝', '隋唐', '宋代', '辽代', '元代', '明代', '清代', '民国', '现代']
    },
    other: {
      label: '其他',
      types: ['全部'],
      eras: ['全部', '战国', '汉晋', '南北朝', '隋唐', '宋代', '辽代', '元代', '明代', '清代', '民国', '现代']
    }
  };

  let activeSource = 'all';
  let activeType = '全部';
  let activeEra = '全部';

  function createFilterButton(value, activeValue, dataAttr, onClick) {
    const btn = document.createElement('button');
    btn.className = 'relic-filter' + (value === activeValue ? ' active' : '');
    btn.dataset[dataAttr] = value;
    btn.textContent = value;
    btn.addEventListener('click', onClick);
    return btn;
  }

  function renderFilterButtons(container, values, activeValue, dataAttr, onClick) {
    const label = container.querySelector('.filter-label');
    container.innerHTML = '';
    container.appendChild(label);
    values.forEach(value => {
      container.appendChild(createFilterButton(value, activeValue, dataAttr, onClick));
    });
  }

  function updateActiveButton(groupSelector, dataAttr, value) {
    document.querySelectorAll(groupSelector).forEach(btn => {
      btn.classList.toggle('active', btn.dataset[dataAttr] === value);
    });
  }

  function filterRelics() {
    relicItems.forEach(item => {
      const itemSource = item.dataset.source;
      const itemType = item.dataset.type;
      const itemEra = item.dataset.era;
      const sourceMatch = activeSource === 'all' || itemSource === activeSource;
      const typeMatch = activeType === '全部' || itemType === activeType;
      const eraMatch = activeEra === '全部' || itemEra === activeEra;
      if (sourceMatch && typeMatch && eraMatch) {
        item.classList.remove('hidden');
      } else {
        item.classList.add('hidden');
      }
    });
  }

  function handleTypeClick(e) {
    activeType = e.currentTarget.dataset.type;
    updateActiveButton('.relic-filter[data-type]', 'type', activeType);
    filterRelics();
  }

  function handleEraClick(e) {
    activeEra = e.currentTarget.dataset.era;
    updateActiveButton('.relic-filter[data-era]', 'era', activeEra);
    filterRelics();
  }

  function handleSourceClick(e) {
    activeSource = e.currentTarget.dataset.source;
    activeType = '全部';
    activeEra = '全部';
    updateActiveButton('.relic-filter[data-source]', 'source', activeSource);
    const config = relicFiltersConfig[activeSource];
    renderFilterButtons(typeFilterGroup, config.types, activeType, 'type', handleTypeClick);
    renderFilterButtons(eraFilterGroup, config.eras, activeEra, 'era', handleEraClick);
    filterRelics();
  }

  // 初始化来源按钮事件
  document.querySelectorAll('.relic-filter[data-source]').forEach(btn => {
    btn.addEventListener('click', handleSourceClick);
  });

  // 初始化类型、年代按钮
  handleSourceClick({ currentTarget: document.querySelector('.relic-filter[data-source="all"]') });

  // 合作机构标签切换
  const partnerTabs = document.querySelectorAll('.partner-tab');
  const partnerPanels = document.querySelectorAll('.partners-panel');

  partnerTabs.forEach(tab => {
    tab.addEventListener('click', function() {
      partnerTabs.forEach(t => t.classList.remove('active'));
      partnerPanels.forEach(p => p.classList.remove('active'));
      this.classList.add('active');
      document.getElementById(this.dataset.tab).classList.add('active');
    });
  });

  // 平滑滚动
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      if (href !== '#') {
        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
          const headerHeight = header.offsetHeight;
          const targetPosition = target.offsetTop - headerHeight;
          window.scrollTo({
            top: targetPosition,
            behavior: 'smooth'
          });
        }
      }
    });
  });
});

// 微信弹窗
function openWechat(event) {
  if (event) event.stopPropagation();
  const modal = document.getElementById('wechatModal');
  if (modal) modal.classList.add('open');
}

function closeWechat() {
  const modal = document.getElementById('wechatModal');
  if (modal) modal.classList.remove('open');
}

// 点击弹窗外部关闭
document.addEventListener('click', function(e) {
  const modal = document.getElementById('wechatModal');
  if (modal && e.target === modal) {
    modal.classList.remove('open');
  }
});

// 动画关键帧
const style = document.createElement('style');
style.textContent = `
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
`;
document.head.appendChild(style);
