
(function(){
  function apply(){
    var dark = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
    var c = dark ? '#93A3A9' : '#5E6B70';
    document.querySelectorAll('.js-plotly-plot').forEach(function(el){
      try{ Plotly.relayout(el, {'font.color': c}); }catch(e){}
    });
  }
  window.addEventListener('load', apply);
  if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', apply);
})();
