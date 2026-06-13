
function getCsrfToken() {
  const tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
  if (tokenInput) return tokenInput.value;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

input = document.getElementById("message-input");
document.addEventListener("DOMContentLoaded", function() {
    const box = document.getElementById("message-scroll-box");
    input.focus();
    box.scrollTop = box.scrollHeight;
    window.scrollTo(document.body.scrollHeight,0);
});
input.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault(); 
        this.form.submit(); 
    }
}); 

function toggleMenu(btn) {
  const menu = btn.nextElementSibling;
  document.querySelectorAll('.message-sent, .message-received').forEach(m => {
    m.style.zIndex = '';
  });
  document.querySelectorAll('.message-actions-menu.open').forEach(m => {
    if (m !== menu) m.classList.remove('open');
  });
  menu.classList.toggle('open');
  if (menu.classList.contains('open')) {
    btn.closest('.message-sent, .message-received').style.zIndex = '10';
  }
}

function copyMessage(btn) {
  const bubble = btn.closest('.message-sent, .message-received')
                    .querySelector('.message-content');
  navigator.clipboard.writeText(bubble.textContent.trim());
  btn.textContent = '✅ Copié !';
  setTimeout(() => btn.textContent = '📋 Copier', 1500);
  btn.closest('.message-actions-menu').classList.remove('open');
  input.focus();
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.message-actions-wrapper')) {
    document.querySelectorAll('.message-actions-menu.open')
            .forEach(m => m.classList.remove('open'));
  }
});

let currentReportUrl = null;

function openReportModal(url) {
  currentReportUrl = url;
  document.getElementById('report-reason-input').value = '';
  document.getElementById('report-modal').classList.add('open');
  document.querySelectorAll('.message-actions-menu.open').forEach(m => m.classList.remove('open'));
  setTimeout(() => document.getElementById('report-reason-input').focus(), 50);
}

function closeReportModal() {
  document.getElementById('report-modal').classList.remove('open');
  currentReportUrl = null;
  console.log('Report modal closed, currentReportUrl reset to null');
  input.focus();
}

function submitReport() {
  const reason = document.getElementById('report-reason-input').value.trim();
  if (!reason) {
    document.getElementById('report-reason-input').focus();
    return;
  }

  const form = document.createElement('form');
  form.method = 'POST';
  form.action = currentReportUrl;

  const csrf = document.createElement('input');
  csrf.type = 'hidden';
  csrf.name = 'csrfmiddlewaretoken';
  csrf.value = getCsrfToken();

  const reasonInput = document.createElement('input');
  reasonInput.type = 'hidden';
  reasonInput.name = 'reason';
  reasonInput.value = reason;

  form.appendChild(csrf);
  form.appendChild(reasonInput);
  document.body.appendChild(form);
  form.submit();
}

function openEditModal(url, content, messageId) {
  currentEditUrl = url;
  console.log('Opening edit modal for message ID:', messageId, 'with content:', content, 'and URL:', url);
  currentEditContent = content;
  document.getElementById('edit-content-input').value = currentEditContent;
  document.getElementById('edit-modal').classList.add('open');
  document.querySelectorAll('.message-actions-menu.open').forEach(m => m.classList.remove('open'));
  setTimeout(() => document.getElementById('edit-content-input').focus(), 50);
}

function closeEditModal() {
  document.getElementById('edit-modal').classList.remove('open');
  currentEditUrl = null;
  currentEditContent = null;
  input.focus();
}

function submitEdit() {
  const new_content = document.getElementById('edit-content-input').value.trim();
  console.log('Submitting edit with new content:', new_content);
  if (!new_content || new_content === currentEditContent) {
    console.log('No changes to submit.');
    document.getElementById('edit-content-input').focus();
    return;
  }

  const form = document.createElement('form');
  form.method = 'POST';
  form.action = currentEditUrl;

  const csrf = document.createElement('input');
  csrf.type = 'hidden';
  csrf.name = 'csrfmiddlewaretoken';
  csrf.value = getCsrfToken();

  const newContentInput = document.createElement('input');
  newContentInput.type = 'hidden';
  newContentInput.name = 'new_content';
  newContentInput.value = new_content;

  form.appendChild(csrf);
  form.appendChild(newContentInput);
  console.log('form : ', form);
  document.body.appendChild(form);
  form.submit();
  
  
}

// Ferme en cliquant sur l'overlay
document.getElementById('edit-modal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeEditModal();
});


document.getElementById('report-modal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeReportModal();
});