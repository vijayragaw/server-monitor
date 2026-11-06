import Swal from 'sweetalert2';
import 'sweetalert2/dist/sweetalert2.min.css';
function options(){const dark=document.documentElement.dataset.theme!=='light';return {target:document.querySelector('.settings-drawer[open]')||document.body,background:dark?'#162239':'#ffffff',color:dark?'#e4eafa':'#17243b',confirmButtonColor:dark?'#667ee8':'#2457d6',customClass:{popup:'monitor-alert'}}}
export function notify(title,text,icon='info'){return Swal.fire({...options(),title,text,icon})}
export function toast(title,icon='success'){return Swal.fire({...options(),title,icon,toast:true,position:'top-end',showConfirmButton:false,timer:2800,timerProgressBar:true})}
export function loading(title,text){Swal.fire({...options(),title,text,allowOutsideClick:false,allowEscapeKey:false,showConfirmButton:false,didOpen:()=>Swal.showLoading()})}

export function emailPrompt(appName){return Swal.fire({...options(),title:'Send a test email',text:`Uses ${appName} SMTP settings. Server acceptance does not confirm inbox delivery.`,input:'email',inputLabel:'Recipient email address',inputPlaceholder:'name@example.com',inputAttributes:{maxlength:254,autocomplete:'email'},showCancelButton:true,confirmButtonText:'Send test email',cancelButtonText:'Cancel',inputValidator:value=>!value||!value.includes('@')?'Enter a valid recipient email address':undefined})}
