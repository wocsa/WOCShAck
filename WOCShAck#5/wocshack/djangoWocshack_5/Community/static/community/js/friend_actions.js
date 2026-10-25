function ConfirmDeleteFriend(form_id, friend_username) {
  if (confirm(`Are you sure you want to delete ${friend_username} from your friends?`)) {
    const form = document.getElementById(form_id);
    form.submit();
  }
}

function ConfirmUnblockFriend(form_id, friend_username) {
  if (confirm(`Are you sure you want to unblock ${friend_username}?`)) {
    const form = document.getElementById(form_id);
    form.submit();
  }
}
function ConfirmBlockFriend(form_id, friend_username) {
  if (confirm(`Are you sure you want to block ${friend_username}?`)) {
    const form = document.getElementById(form_id);
    form.submit();
  }
}