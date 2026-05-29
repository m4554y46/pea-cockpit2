fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const progressDiv = document.getElementById('progressContainer');
  const progressBar = document.getElementById('progressBar');
  const progressMsg = document.getElementById('progressMessage');
  
  progressDiv.style.display = 'block';
  progressBar.style.width = '0%';
  progressMsg.innerText = 'Envoi du fichier...';
  
  const formData = new FormData();
  formData.append('excel', file);
  
  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    progressMsg.innerText = 'Récupération des données financières...';
    progressBar.style.width = '50%';
    
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    
    portfolio = data.portfolio;
    filteredPortfolio = [...portfolio];
    progressBar.style.width = '100%';
    progressMsg.innerText = 'Affichage du portefeuille...';
    buildAll();
    setTimeout(() => {
      progressDiv.style.display = 'none';
    }, 800);
    document.getElementById('apiStatus').innerText = `${portfolio.length} titres importés`;
    document.getElementById('statusDot').classList.remove('loading');
  } catch (err) {
    progressMsg.innerText = `Erreur : ${err.message}`;
    progressBar.style.backgroundColor = 'var(--red)';
    setTimeout(() => {
      progressDiv.style.display = 'none';
      progressBar.style.backgroundColor = 'var(--green)';
    }, 3000);
    alert('Erreur : ' + err.message);
  }
  fileInput.value = '';
});
