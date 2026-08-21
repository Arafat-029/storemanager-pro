; Installateur StoreManager Pro (Inno Setup 6)
;
; Compilation :
;   & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\StoreManagerPro.iss
;
; Produit installer\Sortie\StoreManagerPro-Setup.exe : un fichier unique a
; remettre au client.
;
; Principe : le PROGRAMME va dans Program Files, les DONNEES du magasin dans
; %LOCALAPPDATA%. Une reinstallation ou une mise a jour remplace le premier
; sans jamais toucher aux secondes.

#define AppName        "StoreManager Pro"
#define AppVersion     "1.0.0"
#define AppPublisher   "StoreManager"
#define AppExe         "StoreManagerPro.exe"
#define SourceDir      "..\dist\StoreManagerPro"

[Setup]
AppId={{8F3A6C21-4D7B-4E29-9A15-2C7E5B0D9F44}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=Sortie
OutputBaseFilename=StoreManagerPro-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Program Files exige l'elevation ; sans elle l'installation echouerait a
; mi-parcours plutot qu'au demarrage.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Diagnostic de l'installation"; Filename: "{app}\{#AppExe}"; Parameters: "--check"; Comment: "Vérifie la base de données, l'imprimante et les composants"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--check"; Description: "Vérifier l'installation maintenant"; Flags: postinstall nowait skipifsilent
Filename: "{app}\{#AppExe}"; Description: "Lancer {#AppName}"; Flags: postinstall nowait skipifsilent unchecked

[Code]
const
  // Retour a la ligne. Passe par une constante parce qu'un « # » place en
  // debut de ligne serait pris par le preprocesseur pour une directive.
  NL = #13#10;

var
  PageBase: TInputQueryWizardPage;
  PageMotDePasse: TInputQueryWizardPage;

function Param(Nom, Defaut: String): String;
begin
  // Permet une installation scriptee :
  //   Setup.exe /VERYSILENT /MYSQLPASSWORD=... /MYSQLHOST=...
  // En installation normale, ces parametres sont absents et les valeurs
  // saisies dans l'assistant font foi.
  Result := ExpandConstant('{param:' + Nom + '|' + Defaut + '}');
end;

procedure InitializeWizard;
begin
  PageBase := CreateInputQueryPage(wpSelectTasks,
    'Base de données',
    'Où se trouve la base MySQL du magasin ?',
    'Ces valeurs conviennent dans la plupart des cas. Ne les modifiez que si ' +
    'MySQL a été installé avec des réglages particuliers.');
  PageBase.Add('Serveur :', False);
  PageBase.Add('Port :', False);
  PageBase.Add('Nom de la base :', False);
  PageBase.Add('Utilisateur :', False);
  PageBase.Values[0] := Param('MYSQLHOST', '127.0.0.1');
  PageBase.Values[1] := Param('MYSQLPORT', '3306');
  PageBase.Values[2] := Param('MYSQLDATABASE', 'storemanager');
  PageBase.Values[3] := Param('MYSQLUSER', 'storemanager');

  PageMotDePasse := CreateInputQueryPage(PageBase.ID,
    'Mot de passe de la base',
    'Mot de passe de l''utilisateur MySQL',
    'Saisissez le mot de passe défini lors de la création de l''utilisateur ' +
    'MySQL. Sans lui, l''application ne pourra pas démarrer.');
  PageMotDePasse.Add('Mot de passe :', True);
  PageMotDePasse.Values[0] := Param('MYSQLPASSWORD', '');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PageBase.ID then
  begin
    if Trim(PageBase.Values[0]) = '' then
    begin
      MsgBox('Indiquez le serveur MySQL (127.0.0.1 si MySQL est sur ce PC).', mbError, MB_OK);
      Result := False;
    end
    else if Trim(PageBase.Values[2]) = '' then
    begin
      MsgBox('Indiquez le nom de la base de données.', mbError, MB_OK);
      Result := False;
    end
    else if Trim(PageBase.Values[3]) = '' then
    begin
      MsgBox('Indiquez l''utilisateur MySQL.', mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PageMotDePasse.ID then
  begin
    // En mode silencieux l'assistant ne s'affiche pas : refuser ici
    // interromprait l'installation sans jamais montrer pourquoi. Le mot de
    // passe doit alors venir de /MYSQLPASSWORD=, contrôlé plus bas.
    if WizardSilent then
      Exit;
    if Trim(PageMotDePasse.Values[0]) = '' then
    begin
      // Un mot de passe vide est la cause n1 d'une caisse qui refuse de
      // demarrer : mieux vaut bloquer ici que chez le client.
      MsgBox('Le mot de passe est obligatoire.' + NL + NL +
             'C''est celui que vous avez défini en créant l''utilisateur MySQL.',
             mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function DossierDonnees(): String;
begin
  // {localappdata} pointe sur le profil de l'utilisateur qui LANCE le setup.
  // L'installation etant elevee, c'est bien le compte de la caisse tant que
  // l'installateur est lance depuis sa session.
  Result := ExpandConstant('{localappdata}\StoreManagerPro');
end;

procedure EcrireConfiguration();
var
  Dossier, Fichier: String;
  Lignes: TArrayOfString;
begin
  Dossier := DossierDonnees();
  if not DirExists(Dossier) then
    ForceDirectories(Dossier);

  Fichier := Dossier + '\.env';

  SetArrayLength(Lignes, 8);
  // Commentaires en ASCII pur : SaveStringsToFile ecrit en ANSI, un
  // caractere accentue y ressortirait deforme.
  Lignes[0] := '# Configuration StoreManager Pro';
  Lignes[1] := '# Genere par l''installateur - contient un mot de passe, ne pas partager.';
  Lignes[2] := 'DB_BACKEND=mysql';
  Lignes[3] := 'MYSQL_HOST=' + Trim(PageBase.Values[0]);
  Lignes[4] := 'MYSQL_PORT=' + Trim(PageBase.Values[1]);
  Lignes[5] := 'MYSQL_USER=' + Trim(PageBase.Values[3]);
  Lignes[6] := 'MYSQL_PASSWORD=' + PageMotDePasse.Values[0];
  Lignes[7] := 'MYSQL_DATABASE=' + Trim(PageBase.Values[2]);

  if not SaveStringsToFile(Fichier, Lignes, False) then
    MsgBox('Impossible d''écrire la configuration dans :' + NL + Fichier +
           NL + NL + 'L''application ne pourra pas démarrer.', mbError, MB_OK)
  else if Trim(PageMotDePasse.Values[0]) = '' then
    // Sans mot de passe la caisse ne demarrera pas : le dire maintenant,
    // pendant qu'on est devant la machine.
    MsgBox('Aucun mot de passe de base de données n''a été fourni.' + NL + NL +
           'L''application ne pourra pas démarrer tant que ce fichier ne sera ' +
           'pas complété :' + NL + Fichier, mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    EcrireConfiguration();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Dossier: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Dossier := DossierDonnees();
    if DirExists(Dossier) then
    begin
      // On ne supprime JAMAIS les donnees sans le demander : elles
      // contiennent les ventes, les clients et les sauvegardes du magasin.
      if MsgBox('Supprimer aussi les données du magasin ?' + NL + NL +
                Dossier + NL + NL +
                'Cela effacera les produits, les ventes, les clients et les ' +
                'sauvegardes.' + NL +
                'Répondez Non si vous réinstallez le logiciel.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Dossier, True, True, True);
    end;
  end;
end;
