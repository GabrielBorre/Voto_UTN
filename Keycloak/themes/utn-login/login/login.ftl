<!-- index.html -->
<!DOCTYPE html>
<html lang="es">

<head>
  <meta charset="UTF-8">
  <title>Login UTN FRBA</title>
  <link rel="stylesheet" href="${url.resourcesPath}/css/styles.css">
</head>

<body>
  <header>

  </header>

  <main>
    <section class="login-box">
      <div class="circle">
        <img src="${url.resourcesPath}/img/utn.png" alt="UTN">
      </div>
      <div class="img-utnba">
        <img src="${url.resourcesPath}/img/utn_ba.png" alt="UTN.BA">
      </div>
      <h2>Acceder a tu cuenta</h2>
      <form action="${url.loginAction}" method="post">

        <input type="text" id="username" name="username" required placeholder="Usuario o email">
        <input type="password" id="password" name="password" required placeholder="Contraseña">
        <a href="" style="text-decoration: none;">¿Olvidaste tu contraseña?</a>

        <button type="submit">INICIAR SESIÓN</button>
      </form>
    </section>
  </main>


  <header>

  </header>


  <footer class="disclaimer-academic-footer">
    <p><strong>Descargo de Responsabilidad (Disclaimer):</strong></p>
    <p>Este sitio web es una simulación interactiva desarrollada exclusivamente con fines académicos para el proyecto
      final VOTO UTN.</p>
    <p><strong>No tiene vinculación real ni institucional</strong> con UTN.FRBA
    <p>
    <p>Este formulario no procesa, guarda ni transmite credenciales reales de acceso. Por favor, no introduzca datos
      personales confidenciales.</p>
  </footer>
</body>

</html>
