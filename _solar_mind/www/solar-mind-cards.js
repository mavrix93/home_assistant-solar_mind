/**
 * Solar Mind Custom Cards Bundle
 * This file loads all Solar Mind custom Lovelace cards
 */

// Load individual card modules
const cardModules = [
  'solar-mind-energy-flow-card.js',
  'solar-mind-events-card.js',
  'solar-mind-forecast-card.js',
  'solar-mind-cheapest-hours-card.js',
  'solar-mind-milestones-card.js',
  'solar-mind-health-card.js',
  'solar-mind-away-period-card.js'
];

// Get the base path of this script
const getBasePath = () => {
  const scripts = document.getElementsByTagName('script');
  for (let script of scripts) {
    if (script.src.includes('solar-mind-cards.js')) {
      return script.src.replace('solar-mind-cards.js', '');
    }
  }
  return '/local/solar-mind/';
};

// Load all card modules
const basePath = getBasePath();
cardModules.forEach(module => {
  const script = document.createElement('script');
  script.type = 'module';
  script.src = basePath + module;
  document.head.appendChild(script);
});

console.info(
  '%c SOLAR MIND CARDS %c Loaded ',
  'background: #4caf50; color: white; font-weight: bold;',
  'background: #1c1c1c; color: #4caf50;'
);
