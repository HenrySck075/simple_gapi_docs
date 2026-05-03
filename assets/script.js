(()=>{
  // spa trick stolen from flash (the one for geode-sdk)
  // coincidential idea tho
  async function loadContent(url) {
    const contentUrl = new URL("content.html",url);
    // contains {title: string, desc: string}
    const metaUrl = new URL("metadata.json",url);

    // load content html and inject it into div#content
    const contentResponse = await fetch(contentUrl);
    const contentHtml = await contentResponse.text();
    document.getElementById("content").innerHTML = contentHtml;

    // replace metadata
    const metaResponse = await fetch(metaUrl);
    const meta = await metaResponse.json();
    document.title = meta.title;
    const descMeta = document.querySelector('meta[name="description"]');
    if (descMeta) {
      descMeta.setAttribute("content", meta.desc);
    }
  }

})()
