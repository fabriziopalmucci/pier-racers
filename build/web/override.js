@'
(function () {
  // Se il loader prova a prendere archivi locali su 8000, forziamo il CDN ufficiale.
  // Funziona anche se l'HTML costruisce gli URL in modo dinamico.
  const CDN = "https://pygame-web.github.io/archives/";
  const LOCAL = "http://localhost:8000/archives/";
  const LOCAL2 = "http://127.0.0.1:8000/archives/";

  const _fetch = window.fetch.bind(window);
  window.fetch = function(input, init){
    try{
      if (typeof input === "string") {
        input = input.replace(LOCAL, CDN).replace(LOCAL2, CDN);
      } else if (input && input.url) {
        const u = input.url.replace(LOCAL, CDN).replace(LOCAL2, CDN);
        input = new Request(u, input);
      }
    } catch(e){}
    return _fetch(input, init);
  };

  // anche XHR, per sicurezza
  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url){
    try{
      url = url.replace(LOCAL, CDN).replace(LOCAL2, CDN);
    } catch(e){}
    return _open.apply(this, arguments);
  };
})();
'@ | Out-File -Encoding utf8 "build\web\override.js"
