# Video Producer : guide utilisateur

English: [Video Producer: user guide](/docs?doc=plugin/video-producer/user-guide) (file `docs/user-guide.md`).

Ce guide explique comment réaliser un court film avec Video Producer. Les libellés de l’interface sont écrits en **gras**. Video Producer est livré par étapes. Cette version a l’interface complète, en anglais et en français, enregistre vos projets, importe vos médias et génère de vraies prises et de vrais finals (chapitres 8 et 9), mais certaines fonctions sont encore simulées (chapitre 17). Un chapitre qui décrit quelque chose qui n’existe pas encore se termine par « Disponible à partir de l’étape N ». Le guide d’administration est une page distincte que seuls les admins voient.

## 1. Ce qu’est Video Producer

Video Producer est un plugin PotionUI de montage audiovisuel, de génération de séquences par IA, de direction artistique, de création sonore et de préparation de scènes 3D, dans un même espace. Vous écrivez un synopsis, vous le découpez en plans, vous générez des prises brouillon rapides, vous choisissez la meilleure, vous la passez en final, puis vous montez, raccordez les couleurs, mixez et livrez. Il s’ouvre depuis l’entrée **Video Producer** de la barre latérale.

Avant de commencer :

- Un admin doit avoir préparé au moins un moteur (ce poste, un serveur d’atelier ou un modèle cloud) et au moins un preset vidéo qui vous est attribué. Si la barre Production n’affiche aucun moteur, voyez le chapitre 18.
- Votre admin règle aussi la résolution des brouillons, le nombre de générations que vous pouvez avoir en cours en même temps, et peut limiter les minutes GPU que vous pouvez utiliser par mois.
- La génération est réelle : les prises sont des vidéos produites par les machines ou le compte cloud de votre admin, et elles prennent du temps. L’estimation de la barre Production vous dit à quoi vous attendre avant de commencer (chapitre 8).
- Le modèle MiniMax H3 (les entrées **MiniMax H3** du menu des moteurs) est sous une licence qui exclut son usage, et tout ce qu’il génère, dans l’Union européenne, au Royaume-Uni, aux États-Unis et en Corée du Sud sans autorisation individuelle de MiniMax, et qui demande qu’un produit commercial affiche « MiniMax H3 » de façon visible. Demandez à votre admin avant de l’utiliser. Video Producer ne vérifie rien de tout cela à votre place.

L’interface est en anglais par défaut et existe aussi en français (chapitre 15).

La première fois que vous ouvrez la page, elle crée un projet de départ, « Aube sur le port » (« Dawn at the harbour » en anglais), et l’ouvre. Il contient un synopsis, la direction globale en cinq champs, cinq plans de 5 secondes encore à générer, chacun avec son instruction locale (le port endormi, les mains du pêcheur, le départ, les goélands, vers le large), un titre, un marqueur nommé « Départ » et quatre pistes audio vides. Il n’a ni média, ni prise, ni référence, ni scène 3D. Son nom, son synopsis, les noms de ses plans, son titre et son marqueur sont écrits dans la langue de l’interface ; sa direction globale et ses instructions locales sont écrites dans la langue des prompts du projet, l’anglais par défaut (chapitre 15). Parcourez-y tout le chemin, ou partez d’un projet vide avec **Fichier › Nouveau projet…**. Aux visites suivantes, la page ouvre le projet que vous avez utilisé en dernier (chapitre 5).

## 2. Le parcours en huit étapes

**Aide › Prise en main** montre le même parcours sous forme de liste sur laquelle vous pouvez cliquer. Les huit étapes :

1. **Créer un projet.** **Fichier › Nouveau projet…** (ou **Fichier › Ouvrir…** pour un projet existant). Dans **Propriétés du projet…** vous réglez le nom, le format (16:9, 2.39:1, 9:16, 1:1 ou 4:5), la résolution (720p, 1080p ou 4K) et la cadence (24, 25 ou 30 i/s). Résultat : un projet vide, enregistré au fil de votre travail.
2. **Définir la direction globale.** Dans l’espace **Director IA**, onglet **Direction** : univers et intention, personnages et identité, direction photographique, palette et éclairage, rythme et continuité. Résultat : un texte qui guide toutes les générations.
3. **Ajouter les références.** Dans **Director IA**, onglet **Références** : identités, décors 3D et guides de mouvement. Résultat : ce qui doit rester identique d’un plan à l’autre.
4. **Découper le film en plans.** Dans l’espace **Storyboard** : écrivez le synopsis, cliquez sur **Proposer un découpage**, gardez les plans voulus et ajustez leurs instructions locales. Résultat : une rangée de cartes de plans.
5. **Générer des brouillons.** Dans la barre Production, choisissez le **Moteur de génération**, qualité **Brouillon**, puis **Générer la sélection** (Ctrl+G). L’estimation indique le temps, la mémoire et le quota. Résultat : de vraies prises brouillon A, B, etc., produites par le moteur choisi.
6. **Choisir et passer en final.** Dans l’inspecteur, onglet **Prises** : comparez les prises, cliquez sur **Choisir** pour celle que le plan doit jouer, puis sur **Passer en final** pour la meilleure prise brouillon. Résultat : le plan passe de Brouillon à Final.
7. **Monter, raccorder et mixer.** Fondus sur les clips, raccord de couleur dans l’onglet **Couleur** de l’inspecteur, console dans **Mixage**. Résultat : une séquence terminée.
8. **Préparer la livraison.** **Fichier › Exporter la vidéo…**, **Exporter vers un autre logiciel…** ou **Exporter les sous-titres…**. Résultat : des fichiers à télécharger.

L’interface des huit étapes est en place, et vos projets sont enregistrés au fil de votre travail (chapitre 5). La page ouvre le projet que vous avez utilisé en dernier, ou le projet de départ la première fois (chapitre 1). **Nouveau projet…** démarre un projet vide, « Projet sans titre », et l’ajoute à vos projets. Les brouillons et les finals sont réels depuis l’étape 4. À partir de l’étape 6 : la livraison en fichiers vidéo.

## 3. L’écran

La page compte cinq niveaux de commandes, du plus large au plus local, autour d’un panneau de gauche, d’une zone centrale, de l’inspecteur et de la timeline :

- **Barre de menus.** Dix menus, dans cet ordre : **Video Producer**, **Fichier**, **Édition**, **Montage**, **Plan**, **Production**, **Audio**, **Présentation**, **Fenêtre**, **Aide**. Le menu **Video Producer** contient **À propos de Video Producer**, **Préférences…**, **Raccourcis clavier** et **Rechercher une commande…**. Un menu n’affiche « … » que si la commande ouvre une fenêtre qui demande une saisie, et une coche devant un état activé.
- **Barre projet.** À gauche, le bouton qui affiche ou masque le panneau latéral, le nom du projet (cliquez dessus pour renommer le projet) et son état d’enregistrement (« Enregistrement… », « Enregistré à » et l’heure, « Modifié · cliquer pour enregistrer » ou « Non enregistré — réessayer » ; chapitre 5). Au milieu, le sélecteur d’espaces : **Médias**, **Director IA**, **Storyboard**, **Scène 3D**, **Mixage**. À droite, **Importer**, **Exporter**, **Assistant**, un bouton de recherche des commandes et le bouton qui affiche ou masque l’inspecteur.
- **Barre Production.** Elle cible ce qu’il faut générer et porte le seul bouton principal de la page, **Générer la sélection** (chapitre 8).
- **En-têtes de zone et barre d’outils de la timeline.** Un titre et des compteurs à gauche, de petites icônes à droite.
- **Contenu.** De petits boutons qui apparaissent au survol ou à la sélection.

Une règle à retenir : toutes les autres entrées (Storyboard, panneau latéral, Director IA) ne font que cibler ce qu’il faut générer ; c’est la barre Production qui agit.

Les dix menus regroupent toutes les commandes de la page. La recherche de commande (**Rechercher une commande…**, Ctrl+K) les trouve par leur nom, indique leur menu et leur raccourci, et lance la commande avec Entrée.

| Menu | Ce qu’il contient |
|---|---|
| **Video Producer** | À propos, Préférences, Raccourcis clavier, recherche de commande. |
| **Fichier** | Nouveau projet, Ouvrir, Enregistrer, Historique des versions, Importer des fichiers, Depuis la galerie PotionUI, Propriétés du projet, les trois exports. |
| **Édition** | Annuler, Rétablir, Copier, Coller, Dupliquer, Supprimer, Rechercher un média. |
| **Montage** | Les trois outils, Couper à la tête de lecture, les ajustements du début et de la fin, Modifier la durée, points d’entrée et de sortie, Effacer la plage, Ajouter un marqueur, Ajouter un titre, Fondus d’entrée et de sortie. |
| **Plan** | Nouveau plan, Informations, Afficher la source, Prises du plan, Passer la prise en final, Couleur du plan, Raccorder la couleur au plan précédent, Images clés de caméra, Favori, Rejeter, Retirer la marque. |
| **Production** | Direction globale, Découper le synopsis en plans, Contrôle de continuité, Générer la sélection, Qualité brouillon et finale, la file, Annuler la génération, Résultats et prises, Assembler les prises choisies, Atelier avancé, le moteur, le Hybrid builder. |
| **Audio** | Ajouter une piste audio, Importer un fichier audio, Console de mixage, Voix et dialogues et l’atelier Sound design. |
| **Présentation** | Lecture, boucle, plein écran, guides de cadrage, Comparer les prises, Scope de luminance, Indicateurs audio, zoom de la timeline, Magnétisme. |
| **Fenêtre** | Les cinq espaces, les espaces de références, Panneau latéral, Inspecteur, Assistant PotionUI, Bibliothèque de prompts, Index de la timeline, Tâches en arrière-plan. |
| **Aide** | Prise en main, Raccourcis clavier, Rechercher une fonctionnalité, Fonctions simulées. |

### Les zones de la page

- **Panneau de gauche.** Il change avec l’espace (chapitre 4). Affichez-le ou masquez-le avec le premier bouton de la barre projet ou avec Ctrl+Alt+1.
- **Centre.** Le visualiseur, les cartes du storyboard, la planche de références ou la vue 3D, selon l’espace.
- **Inspecteur.** À droite. Il suit la sélection (chapitre 7). Il démarre masqué quand la fenêtre fait moins de 1360 pixels de large : ouvrez-le avec le dernier bouton de la barre projet, ou sélectionnez quelque chose, ce qui l’ouvre.
- **Timeline.** En bas. Dans **Mixage**, la console de mixage prend sa place et un bouton ramène la timeline. Glissez la fine ligne au-dessus de la barre Production pour lui donner plus ou moins de hauteur.
- **Barre d’état.** Tout en bas, de gauche à droite : le rappel de la langue (`EN` ou `FR` ; cliquez dessus pour ouvrir les Préférences), le nombre de plans avec la durée, la résolution et le format d’image, l’outil actif, la sélection, la plage. À droite : le nombre de points de direction à vérifier (cliquez dessus pour ouvrir l’onglet **Direction**), la file de génération, le magnétisme et, si votre admin vous a fixé une limite, votre **Quota GPU**, les minutes utilisées ce mois-ci rapportées à cette limite (les fournisseurs cloud sont facturés à part).

Le visualiseur a sa propre barre de transport : volume de contrôle, retour au début, image précédente et suivante, lecture, boucle, le timecode, guides de cadrage, format d’image, résolution et plein écran. Quand vous prévisualisez une prise, une comparaison ou un média source, une pastille en haut du visualiseur vous ramène à la séquence avec **Revenir à la séquence**.

La timeline a une barre d’outils et une rangée par type d’élément. La barre d’outils contient **Annuler** et **Rétablir**, les trois outils (**Outil Sélection**, **Outil Plage**, **Outil Lame**), **Couper à la tête de lecture**, **Dupliquer**, **Supprimer**, le menu **Ajouter** (**Prompt**, **Frame de référence**, **Control video**, **Titre**, **Marqueur**, **Piste audio**), **Magnétisme**, le zoom et **Ajuster**. Les rangées sont **Titres**, **Prompts**, **Frames**, **Control video**, **Plan 3D**, **V1 · Vidéo** et une rangée par piste audio, avec **M** (muet) et **S** (solo). Cliquez sur la règle pour déplacer la tête de lecture ; avec l’outil Plage, ou en glissant avec Alt enfoncée, tracez une plage. Glissez un plan pour changer son ordre, glissez ses bords pour le raccourcir ou le rallonger (les plans suivants suivent), glissez les poignées blanches en haut d’un clip pour régler ses fondus, glissez un clip audio vers une autre piste. Ctrl et la molette zooment. Double-cliquez sur un endroit vide de la rangée Prompts, Frames ou Control video pour y créer un élément.

## 4. Les espaces de travail

Chaque espace change le panneau de gauche et le centre. L’inspecteur, à droite, suit votre sélection dans tous. **Fenêtre › Index de la timeline** liste les prompts, frames, marqueurs et Control video avec leur position, et **Fenêtre › Tâches en arrière-plan** montre la génération en cours et la file.

### Médias

Les médias du projet dans un seul panneau. Un nouveau projet n’en a aucun : le panneau indique « Aucun média dans ce projet. » et propose **Importer des médias**, comme le bouton d’import de son en-tête et **Importer** dans la barre projet ; le chapitre 6 explique comment faire entrer vos images, vidéos et fichiers audio. Filtrez avec les pastilles de collections (**Toutes**, **Images**, **Vidéos**, **Audio**, **Générés**), cherchez par nom sans vous soucier des accents, double-cliquez pour prévisualiser, glissez vers la timeline. Pour un élément sélectionné, le panneau indique sa durée, son format, sa collection et son origine, et propose **Prévisualiser**, **Au montage** et, pour les images et les vidéos, **Utiliser comme frame à la tête de lecture**. Le centre est le visualiseur.

### Director IA

Le panneau de gauche a trois onglets. Un point sur **Direction** signale qu’il y a des points à vérifier, et **Résultats** affiche le nombre de prises.

- **Direction.** Montre ce qui guide la génération sur la plage courante : la direction globale, l’instruction locale, les références et Control video, avec **Voir le récapitulatif de génération**. En dessous : **Points à vérifier**, la liste des contradictions de direction et des raccords de couleur à corriger, le **Profil H3 du projet** (FL2VA, Ref2VA ou Hybrid AV, chapitres 8 et 11) et la **Direction globale** elle-même, en cinq champs (univers et intention, personnages et identité, direction photographique, palette et éclairage, rythme et continuité), avec un compteur sur 4000 caractères. Chaque champ a un lien **Bibliothèque & assistant**. Le bouton en forme d’engrenage, **Paramètres H3**, ouvre l’**Atelier avancé**.
- **Références.** Trois familles : **Images et identité**, **Décors 3D** et **Guides de mouvement**. Une référence est globale (elle accompagne toutes les générations) ou ne s’applique qu’à une plage ; **Associer à la plage** règle le second cas. **Référence** en ajoute une. Le centre montre la planche de références, en deux groupes, **Direction globale** et **Sur la timeline**, avec un champ de recherche. Glissez une vignette sur la piste Frames pour l’ancrer à un moment précis. Un nouveau projet n’a aucune référence : la planche le dit, et **Référence** ajoute la première.
- **Résultats.** Les cartes de prise de chaque plan (chapitre 9), la **File de génération** et **Assembler les prises choisies**.

### Storyboard

À gauche : le **Synopsis** (une phrase devient un plan) et **Proposer un découpage**. Le **Découpage proposé** liste les plans : cochez ceux à garder, renommez-les et cliquez sur **Ajouter N plans à la fin**. Dans cette version, le découpage est simulé : il se contente de couper le synopsis en phrases. Puis **À produire**, avec **Brouillons restants** et **Passage en final** (le nombre de plans et la durée qu’il reste à faire pour chacun), et **Continuité**, qui liste les raccords de couleur à vérifier, chacun avec **Raccorder la couleur**.

Au centre : une carte par plan, dans l’ordre, avec son numéro, sa durée, son nom, son étape (**Source**, **À générer**, **Brouillon** ou **Final**), son nombre de prises et son instruction locale ; cliquez sur l’instruction pour l’écrire. Glissez une carte pour la déplacer. Les boutons d’une carte apparaissent au survol ou quand la carte est sélectionnée : le bouton principal suit l’étape, **Générer**, **Passer en final**, **Voir les prises** ou **Régénérer**, et trois icônes montrent le plan dans le visualiseur, insèrent un plan après lui et le suppriment. Tant qu’une prise du plan est en cours, la carte montre son étape et sa progression, et le bouton est désactivé. L’en-tête compte les plans par étape, en ajoute un avec **Plan** et règle la taille des vignettes ; une tuile **Nouveau plan** à la fin fait la même chose. Dans cet espace, les flèches gauche et droite déplacent la sélection vers le plan précédent ou suivant.

### Scène 3D

Un nouveau projet n’a aucune scène 3D. Dans le panneau de gauche, la liste des **Scènes** est vide : **Scène d’essai** crée un nuage de points procédural, marqué **Simulé**, et **Référencer un fichier Gaussian Splat…** demande le chemin d’un fichier et l’ajoute comme scène. Viennent ensuite les **Plans 3D sur la timeline** (**Nouveau plan 3D à la tête de lecture**), les **Trajectoires prédéfinies** (**Orbite**, **Travelling avant**, **Élévation**), la caméra et ses positions clés dans l’inspecteur, et les **Sorties pour la génération** : **Capturer une frame** et **Générer la Control video**. Le centre est la vue 3D (avant toute scène, elle indique « Aucune scène 3D » et propose **Scène d’essai**) : glissez pour orbiter, utilisez la molette pour la distance, lancez la lecture pour prévisualiser la trajectoire. Cet espace est en partie simulé : voyez le chapitre 17.

### Mixage

L’**Atelier Sound design**, les **Sons du projet** (glissez-en un vers une piste, ou utilisez son bouton plus pour l’ajouter à la tête de lecture), les **Rôles** (**Dialogue**, **Musique**, **Ambiance**, **SFX**) avec leur nombre de pistes, et la console de mixage, qui prend la place de la timeline : faders, **M** et **S**, panoramique, égaliseur, compresseur, filtre, envois de réverbération et de délai, vumètres et un mode d’automation. Le centre est le visualiseur. Les quatre pistes d’un nouveau projet sont vides, et **Sons du projet** indique « Aucun son dans ce projet. » tant que vous n’en importez pas (chapitre 6). La console joue les fichiers audio que vous importez (chapitre 13) ; les sons que l’atelier prépare sont synthétisés par votre navigateur. L’atelier et les courbes d’automation sont simulés : voyez le chapitre 17.

## 5. Projets

Vos projets sont enregistrés sur le serveur PotionUI, dans votre compte, au fil de votre travail. Il n’y a aucun fichier à garder ni rien à exporter pour ne pas les perdre. La page ne liste que vos propres projets.

### Ouverture de la page

La page ouvre le projet que vous avez utilisé en dernier. S’il n’existe plus, elle ouvre votre projet modifié le plus récemment. Si vous n’en avez aucun (première visite, ou vous les avez tous supprimés), elle crée le projet de départ (chapitre 1) et l’ouvre.

### Enregistrement

La page enregistre toute seule, moins d’une seconde après votre dernière modification. La barre projet montre l’état sous le nom du projet :

| État | Sens |
|---|---|
| « Enregistré à » et l’heure | Ce que vous voyez est ce qui est enregistré. |
| « Modifié · cliquer pour enregistrer » | Vous avez fait une modification pas encore enregistrée. Elle l’est un instant plus tard ; cliquez sur l’état pour enregistrer tout de suite. |
| « Enregistrement… » | L’enregistrement est en cours. |
| « Non enregistré — réessayer » | L’enregistrement a échoué. Un message dit pourquoi, avec un bouton **Réessayer** ; cliquez sur l’état pour réessayer. La modification suivante réessaie aussi, et vos changements restent dans la page. |

**Fichier › Enregistrer** (Ctrl+S) enregistre tout de suite et affiche « Projet enregistré ». La page essaie aussi d’enregistrer quand vous passez à un autre onglet du navigateur et quand vous la quittez. Pour renommer le projet, cliquez sur son nom dans la barre projet : le nom est enregistré avec le projet et apparaît dans la liste.

Un enregistrement qui échoue affiche l’un de ces trois messages : « Impossible d’enregistrer le projet. » (erreur réseau ou serveur), « Le projet n’a pas pu être enregistré : son contenu a été refusé. » ou « Le projet est trop volumineux pour être enregistré. » (les données d’un projet, sans les fichiers de médias, sont limitées à 4 Mio). Réessayer ne règle pas les deux derniers : voyez votre admin.

### Ouvrir

**Fichier › Ouvrir…** (Ctrl+O) ouvre la fenêtre **Ouvrir un projet**. Elle liste vos projets, le plus récemment modifié en premier. Chaque ligne montre le nom du projet, puis la date de modification, le nombre de plans et la durée. Le projet ouvert porte le badge **Actuel**. Une capture de cette fenêtre, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/open-window.png`.

- Sélectionnez une ligne, puis cliquez sur **Ouvrir**. Un double-clic sur une ligne ou Entrée dessus font la même chose. **Ouvrir** est désactivé tant que la ligne sélectionnée est le projet déjà ouvert. La page enregistre le projet courant avant d’en ouvrir un autre. Si cet enregistrement a échoué et que des modifications attendent, une fenêtre « Modifications non enregistrées » dit que ces modifications n’ont pas pu être enregistrées et seront perdues : **Abandonner les modifications** continue, et annuler garde le projet ouvert.
- **Nouveau projet** (en bas à gauche) crée un projet vide, comme **Fichier › Nouveau projet…**.
- L’icône de corbeille au bout d’une ligne supprime ce projet, après une confirmation qui précise que le projet et ses versions seront supprimés et que cette action est irréversible. Le projet ouvert n’a pas de corbeille. Supprimer un projet annule les prises qu’il a encore en cours. Cela ne supprime ni les médias de votre bibliothèque ou de votre galerie, ni les vidéos de ses prises, qui restent dans votre historique de générations.
- La fenêtre indique « Chargement des projets… » pendant le chargement, « Aucun projet enregistré » quand vous n’en avez pas, et « Impossible de charger vos projets. » avec un bouton **Réessayer** quand le serveur n’a pas répondu.

**Fichier › Nouveau projet…** enregistre le projet courant, puis crée un projet vide, « Projet sans titre », l’ouvre et affiche « Nouveau projet vide créé ». Elle ne demande une confirmation (**Créer un projet vide**) que si le projet courant n’a pas pu être enregistré.

### Historique des versions

**Fichier › Historique des versions…** ouvre la fenêtre **Historique des versions** (« Chaque enregistrement crée une version »). Elle liste les versions du projet ouvert, la plus récente en premier. Chaque ligne montre le numéro (« Version 7 »), la date et l’heure, secondes comprises, et le nombre de plans. Une capture de cette fenêtre, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/version-history.png`. Une version issue d’une restauration ajoute « Restaurée depuis la version N ». La version sur laquelle vous travaillez porte le badge **Actuelle** et ne peut pas être sélectionnée.

Pour revenir en arrière, sélectionnez une version plus ancienne et cliquez sur **Restaurer**. Une fenêtre demande de confirmer (« Restaurer la version N » : le projet revient à cette version et l’état actuel reste dans l’historique). Si le dernier enregistrement a échoué et que des modifications attendent, une seconde fenêtre, « Modifications non enregistrées », demande de confirmer qu’elles sont perdues (**Abandonner les modifications**). Ensuite le projet devient cette version et la page affiche « Version N restaurée ». La restauration est elle-même une nouvelle version en haut de la liste : rien n’est perdu et vous pouvez restaurer l’état d’où vous veniez. **Annuler** ferme la fenêtre.

Votre admin limite le nombre de versions conservées par projet (50 par défaut) et les plus anciennes sont supprimées en premier. Chaque enregistrement qui modifie le projet crée une version et la page enregistre souvent : la limite peut être atteinte vite, demandez à votre admin de la relever si vous voulez un historique plus long.

### Quand le projet a changé ailleurs

Si vous ouvrez le même projet dans deux onglets, deux fenêtres ou sur deux appareils, la page qui enregistre en second est partie d’une version périmée et le serveur refuse son enregistrement. Cette page charge alors la version enregistrée du projet et affiche « Projet rechargé : il a été modifié ailleurs ». Les modifications que vous n’aviez pas enregistrées dans cette page sont perdues, et rien n’est fusionné. Travaillez sur un projet à un seul endroit à la fois. **Fichier › Historique des versions…** permet de retrouver un état antérieur si besoin.

### Quand le projet a été supprimé ailleurs

Si vous supprimez le projet depuis un autre onglet ou un autre appareil pendant qu’il est ouvert ici, l’enregistrement suivant est refusé parce que le projet n’existe plus. La page cesse de l’enregistrer, affiche « Ce projet a été supprimé ailleurs », puis ouvre votre projet modifié le plus récemment, ou crée le projet de départ si vous n’en avez aucun. Si cela échoue, la page affiche « Impossible d’ouvrir Video Producer » avec un bouton **Réessayer**. Les modifications que vous n’aviez pas enregistrées sont perdues.

### Annuler et rétablir

**Édition › Annuler** et **Rétablir** (Ctrl+Z, Ctrl+Shift+Z) portent sur les modifications faites dans la page, jusqu’à 100 étapes. L’historique est gardé dans la page, pas dans le projet : recharger la page, ouvrir un autre projet, créer un projet, restaurer une version et un rechargement après un conflit le vident tous. Une annulation est une modification comme une autre, et elle est enregistrée aussi.

## 6. Médias

Les médias d’un projet sont les images, vidéos et fichiers audio que vous avez importés, et les prises du projet (chapitre 9). L’espace **Médias** les liste (chapitre 4).

### Importer

- **Images et vidéos.** **Fichier › Importer des fichiers…** (Ctrl+I), **Importer** dans la barre projet, le bouton d’import de l’en-tête du panneau Médias et **Importer des médias** dans un panneau vide ouvrent la fenêtre **Importer des images et des vidéos**. C’est le sélecteur PotionUI de votre bibliothèque : les fichiers que vous avez téléversés dans PotionUI et les générations que vous y avez copiées.
- **Depuis la galerie.** **Fichier › Depuis la galerie PotionUI** ouvre **Importer depuis la galerie**, avec vos générations passées. Chaque fichier d’une génération se choisit séparément. Seules les images et les vidéos peuvent être choisies.
- **Audio.** **Audio › Importer un fichier audio…**, le bouton **Son** des **Sons du projet** dans l’espace **Mixage** et le bouton **Importer** de la console ouvrent **Importer des fichiers audio**, le sélecteur de votre bibliothèque limité à l’audio.

Dans chaque sélecteur, cochez plusieurs fichiers et confirmez-les ensemble. Les fichiers apparaissent alors dans le panneau Médias et la page affiche, par exemple, « 2 fichiers importés ». Un média déjà présent dans le projet (même origine) n’est pas importé de nouveau : la page le compte à part, par exemple « 2 fichiers importés · 1 fichier déjà présent dans le projet », ou « 1 fichier déjà présent dans le projet » quand rien n’est nouveau. Quand certains ne peuvent pas être importés, elle ajoute, par exemple, « 1 fichier n’a pas pu être importé » : le fichier n’est plus disponible, ou son type n’est pas accepté par la fenêtre. Si votre serveur n’a pas de sélecteur, la page indique « Le sélecteur de médias n’est pas disponible sur ce serveur. »

Un import ne copie rien : le projet garde une référence à l’élément de la bibliothèque ou au fichier de la galerie, et l’adresse que la page utilise pour l’afficher. Si vous supprimez le fichier de PotionUI, le projet ne peut plus l’afficher ni le lire.

### Dans le panneau Médias

Après l’import, votre navigateur lit la durée et la taille de chaque fichier. La durée s’affiche en bas à droite de la vignette. Pour l’élément sélectionné, le panneau montre **Durée**, **Format**, **Collection** et **Origine** : **Galerie** ou **Bibliothèque** ; la vignette porte le même mot. La cadence d’une vidéo importée vient de la bibliothèque quand elle la connaît, et s’affiche après la taille (par exemple « 1280×720 · 25 i/s ») ; sinon, et pour un fichier de la galerie, **Format** n’indique que la taille. Les pastilles de collections rangent les images sous **Images**, les vidéos sous **Vidéos** et les fichiers audio sous **Audio**. **Générés** contient les vidéos des prises terminées du projet (chapitre 9). Une capture du panneau après un import se trouve dans `docs/screenshots/media-import.png`.

### Vignettes

Une image est sa propre vignette. Pour une vidéo, la page utilise la vignette que PotionUI a faite quand il y en a une, sinon une image que votre navigateur capture dans le fichier. Les vignettes ne sont pas enregistrées dans le projet : elles sont refaites à l’ouverture du projet. Elles s’affichent partout où un média ou un plan montre son image : le panneau Médias, l’inspecteur, la timeline et le visualiseur.

### Lecture

- **Vidéo et images.** Mettez le média au montage (**Au montage**, ou glissez-le vers la timeline). Le visualiseur lit alors la vraie vidéo en suivant la tête de lecture, ou affiche l’image, avec les fondus et les réglages de couleur du plan. Pour regarder un média seul, double-cliquez dessus ou cliquez sur **Prévisualiser** : le visualiseur le montre, une vidéo avec les commandes de votre navigateur et un fichier audio avec un lecteur audio, et **Revenir à la séquence** vous y ramène.
- **Son d’une vidéo.** Le visualiseur ne lit pas le son d’une vidéo. Le son vient des pistes audio (chapitre 13).
- **Audio.** Un fichier audio placé sur une piste passe par sa tranche de la console. Les faders, muet et solo, panoramique, égaliseur, compresseur, filtre et envois agissent sur le vrai son, les vumètres le montrent, et le clip dessine la forme d’onde du fichier dans la timeline (chapitre 13).

Ce qui reste simulé : les prises faites par les versions antérieures d’un projet, qui montrent une vignette procédurale marquée Simulé, et les sons de l’atelier Sound design, que votre navigateur synthétise (chapitre 17). Les prises de la génération réelle sont des vidéos ordinaires et se lisent comme n’importe quelle vidéo (chapitre 9).

## 7. Inspecteur

L’inspecteur suit la sélection et son titre dit ce qui est sélectionné : **Plan vidéo**, **Clip audio**, **Titre**, **Instruction locale**, **Frame de référence**, **Control video**, **Plan 3D**, **Marqueur**, **Référence** ou **Tranche de console**. Pour un plan, il commence par une vignette, le nom (cliquez dessus pour renommer le plan), l’étape et les temps, et il a trois onglets :

- **Plan.** Un raccourci vers l’action suivante (**Générer des brouillons**, ou **Passer la prise A en final**) avec le moteur qu’il utilisera (« Sur » suivi du moteur), **Durée et source** (la durée, l’endroit où le plan commence dans sa source et la longueur de la source), **Fondus** (**Entrée** et **Sortie**), la **Marque** (**Aucune**, **Favori** ou **Rejeté**) et trois icônes pour couper le plan au milieu, le dupliquer et le supprimer.
- **Prises.** Les cartes de prise du plan, en **Finales** et **Brouillons**, et un bouton qui fait des brouillons de plus (par exemple « 2 brouillons de plus » ; chapitre 9).
- **Couleur.** Le scope de luminance, le raccord avec le plan précédent, les préréglages et les réglages fins (chapitre 12).

Les autres éléments ont leur propre panneau :

- **Clip audio :** sa piste, son début, sa durée, son gain, ses fondus, et un bouton qui ouvre sa tranche dans la console.
- **Titre :** le texte, le sous-titre, le début et la durée.
- **Instruction locale :** le texte, le lien **Bibliothèque & assistant**, le bouton **Éditeur**, les avertissements sur la direction, le début, la durée, l’influence, et la direction globale appliquée.
- **Frame de référence :** l’image (choisie parmi les images du projet, qu’un nouveau projet n’a pas), la position, le rôle (début, fin, transition, identité, style, capture 3D) et l’intensité de son influence.
- **Control video :** le nom, sa source (**Scène 3D** ou **Vidéo importée**), le début, la durée et la force de son guidage. Sur sa plage, le mouvement vient du guide : les instructions de caméra des prompts sont ignorées.
- **Plan 3D :** la scène, le début, la durée et la **Caméra**.
- **Marqueur :** le libellé et la position.
- **Référence :** le nom, le rôle, la portée (**Direction globale** ou **Moment précis**) et le plan concerné.
- **Tranche de console :** le nom, le rôle, les effets (**Égaliseur**, **Compresseur**, **Filtre**) et les envois.

Dans l’espace **Scène 3D**, avec un plan 3D sélectionné ou sans sélection, l’inspecteur affiche la **Caméra** : focale, orientation, inclinaison, distance et hauteur cible, **Position clé**, **Suivre la trajectoire** et la liste des positions clés. Sans sélection dans les autres espaces, il montre le projet (format, profil H3, contenu), un rappel des principaux raccourcis et un bouton **Propriétés du projet…**.

## 8. Barre Production et génération

La barre Production se lit comme une phrase : une cible (**Plan**, **Plage** ou **Séquence**), la plage avec le nombre de plans et de prompts qu’elle contient, une qualité (**Brouillon** ou **Final**), un mode de sortie, le **Moteur de génération**, l’**Atelier avancé**, puis l’estimation, **Ajouter à la file** et **Générer la sélection**. Un nombre accompagné d’une icône d’alerte après les compteurs est le nombre de contradictions de direction dans la plage ; cliquez dessus pour les voir. La génération est réelle : une prise est une vidéo produite en arrière-plan par le moteur que vous choisissez.

### Choisir le moteur

- Le mode de sortie **Génération IA** est le mode réel. **Rendu 3D** et **Rendu 3D + IA** sont encore simulés (chapitre 17) ; avec **Rendu 3D**, le bouton principal devient **Préparer le rendu**.
- Le menu **Moteur de génération** liste ce que votre admin a activé et vous a attribué, en groupes qui portent le nom des backends. Un groupe au nom du backend de votre admin contient les presets vidéo qui tournent sur son matériel, par exemple **Wan 2.1 / 2.2** ou **MiniMax H3**. Chaque fournisseur cloud a son groupe, avec ses modèles vidéo par leur nom. Votre choix est enregistré avec le projet. Que le preset tourne sur ce poste ou sur un serveur d’atelier, c’est PotionUI qui le décide, et la carte de la prise vous le dit ensuite. Survolez le menu pour voir le groupe et, pour un preset qui tourne sur le matériel de l’admin, la mémoire libre de son GPU (« 16,0 / 24,0 Go libres »). Sur une fenêtre de moins de 1400 pixels de large, le menu est masqué : utilisez **Production › Moteur de génération…**, qui ouvre l’**Atelier avancé** sur son étape du moteur. Une capture du menu et de la barre qui l’entoure, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/engine-popup.png`.
- Sans moteur, le menu indique « Aucun moteur » et la barre dit « Aucun moteur de génération : un administrateur doit activer un preset vidéo ou un modèle cloud. » Un admin voit aussi le lien « Ouvrir les réglages du plugin ». Quand le moteur d’un projet n’est plus disponible, le menu indique « Moteur plus disponible » et la barre dit « Le moteur de ce projet n’est plus disponible : choisissez-en un autre. » Un projet d’une version antérieure qui nommait un moteur fictif est ramené au vrai moteur correspondant à son ouverture.
- **Qualité.** **Brouillon** fait des prises rapides à la résolution choisie par votre admin, ou à la plus proche que le moteur propose ; survolez-le pour la voir (« Brouillon rapide en 832×480 : valider mouvement et cadrage »). **Final** fait des prises à la plus grande résolution du moteur (« Qualité finale en 1280×720 : à réserver aux prises retenues »). Pour améliorer un brouillon qui vous plaît, **Passer en final** (chapitre 9) est en général le meilleur moyen : il garde l’image que vous avez choisie.
- L’**Atelier avancé** a trois étapes : **Sources et guides**, **Moteur et Hybrid builder** et **Son et livraison**. Il s’ouvre depuis la barre, depuis **Production › Atelier avancé…** et, pour le moteur, depuis **Paramètres H3** dans Director IA. Son champ **Variantes par fenêtre** (de 1 à 4) règle le nombre de prises, A, B, etc., que chaque plan reçoit à la génération. Les réglages que le moteur n’utilise pas y sont grisés et portent le badge « Non transmis à ce moteur » (chapitre 17).

### Lire l’estimation

L’estimation se trouve à droite de la barre dès qu’un moteur est choisi : une ligne courte avec le temps, la mémoire (un modèle cloud n’en a pas) et, sur une fenêtre large, les minutes de quota ou, pour les admins, le coût. Survolez-la pour le détail. Elle suit vos modifications une demi-seconde après que vous vous êtes arrêté, une fois le projet enregistré : d’ici là elle indique « L’estimation se met à jour une fois le projet enregistré. » et, pendant le calcul, « Estimation… ». Le détail comporte ces lignes :

- **Portée.** Les plans, les variantes et la résolution : « 2 plans × 2 variantes en 832×480 ».
- **Temps.** « Temps ≈ 4 min sur MiniMax H3 (mesuré sur 3 prises) ». Il vient des prises déjà faites avec le même preset, le même moteur et la même résolution, dont la durée réelle a été mesurée : c’est la calibration. Tant qu’il n’y en a pas, on lit « Temps : — (pas encore de mesure sur MiniMax H3) » et la barre affiche « — ». Il se remplit après quelques générations.
- **Mémoire.** « Mémoire ≈ 22,5 Go, 16,0 Go libres sur Local Generation ». C’est une estimation d’après la taille des fichiers de modèle, jamais une garantie. « Mémoire : inconnue » quand elle n’a pas pu être estimée.
- **Quota.** Vos minutes GPU Video Producer mensuelles : « Quota : 5 min nécessaires, 40 min restantes sur 60 ce mois-ci », « Quota : exempté » si vous êtes exempté, et « Cloud : aucun quota GPU consommé » pour un modèle cloud, qui n’en consomme pas. Il s’affiche en **Quota GPU** dans la barre d’état quand votre admin vous a fixé une limite. Quand vos minutes sont limitées, les minutes d’une prise sont réservées à sa création et ajustées à sa durée réelle quand elle se termine ; une prise qui échoue ou qui est annulée les rend. Sans limite, ou si vous êtes exempté, aucune minute n’est réservée ni ajustée. Tant qu’un preset n’a pas été mesuré, chaque seconde de vidéo compte pour 10 secondes de GPU.
- **Coût.** Pour les admins seulement, avec un modèle cloud : « Coût ≈ » suivi du montant, ou « Coût : inconnu pour ce modèle » quand le fournisseur ne publie pas de prix.

### Blocages et avertissements

Ce qui bloque **Générer la sélection** (le bouton est désactivé et la barre affiche la première raison ; survolez-la pour les voir toutes) :

- aucune plage valide ;
- ni direction globale ni instruction locale dans la plage ;
- une instruction locale vide dans la plage ;
- un mode de sortie 3D sans plan 3D dans la plage ;
- aucun moteur, ou un moteur qui n’est plus disponible ;
- un preset absent ou qui ne vous est plus attribué (« Ce preset est absent ou ne vous est plus attribué. ») ;
- un profil que le moteur ne sait pas générer (« Wan 2.1 / 2.2 ne sait pas générer le profil Ref2VA : passez en FL2VA ou sur MiniMax H3. ») ;
- des fichiers de modèle que votre admin n’a pas installés (« Modèles à installer pour ce preset : … ») : demandez-les-lui ;
- un moteur cloud sans modèle (« Choisissez un modèle cloud pour ce moteur. ») ;
- un plan en Ref2VA sans aucune référence à envoyer (« “Plan 2” n’a pas de référence : Ref2VA en demande au moins une pour ce plan. ») ;
- un quota épuisé (« Quota GPU dépassé : 5 min nécessaires, 2 min restantes ce mois-ci. ») : passez à une qualité moins chère, à une plage plus courte ou à un modèle cloud.

Les boutons d’un seul plan (sur une carte du Storyboard, dans l’inspecteur, dans le visualiseur) n’attendent pas l’estimation, mais le serveur de votre admin applique les mêmes règles et la page affiche la première raison dans un message.

Ce qui avertit seulement, sans bloquer :

- une estimation de mémoire supérieure à celle du GPU : « Passera par la RAM de l’hôte, plus lent. » Les poids passent par la mémoire du serveur. La génération continue, plus lentement, et échoue si le serveur manque de mémoire pour cela (chapitre 18) ;
- le profil FL2VA sans frame liée à un plan : « “Plan 2” n’a pas de frame liée : il sera généré à partir du texte seul. » La génération continue à partir du texte, et la carte de la prise indique « texte seul » ;
- un plan plus long que ce que le moteur permet : « “Plan 2” dépasse la durée permise par ce moteur : il sera coupé à 15 s. »

Deux remarques n’apparaissent que dans l’infobulle de l’estimation : « La mémoire nécessaire n’a pas pu être estimée. » et « Aucun temps mesuré pour ce moteur et cette résolution. »

### Générer

**Générer la sélection** (Ctrl+G) enregistre le projet et lance une prise par plan et par variante, chacune avec sa propre graine. Un plan est construit à partir de son instruction locale suivie des champs remplis de la direction globale, et de ses frames et références, selon le profil (voir plus bas). Si le projet n’a pas pu être enregistré, rien ne démarre (« Le projet n’a pas pu être enregistré : génération non lancée. »).

- Les boutons d’un seul plan lancent des brouillons pour ce plan seulement : **Générer** sur une carte du Storyboard, **Générer des brouillons** dans l’inspecteur et le visualiseur, et « 1 brouillon de plus » (ou « 2 brouillons de plus ») dans l’inspecteur, onglet **Prises**.
- Tant que des prises sont en cours, **Générer la sélection** est refusé avec « Une génération est déjà en cours. » La barre affiche alors la progression et **Annuler**. Un plan qui n’a aucune prise en cours peut encore être lancé par ses propres boutons.
- Votre admin limite le nombre de générations que vous pouvez avoir en cours en même temps. Les prises au-delà attendent en **En file** et démarrent d’elles-mêmes, l’une après l’autre, quand les autres se terminent.
- **Ajouter à la file** garde la plage courante pour plus tard. Les fenêtres en file sont listées sous **File de génération** dans Director IA, onglet **Résultats**, et comptées dans la barre d’état. **Générer la file** les lance et **Vider** efface la liste. Cette liste vit dans votre page : elle n’est pas enregistrée avec le projet.

### Suivre les prises

- Chaque prise affiche son état : **En file**, **En cours** (avec l’étape et le pourcentage), **Échec**, **Annulée**, ou, une fois terminée, sa durée. La barre affiche l’étape et la progression de l’ensemble du lot, la carte du Storyboard affiche la progression de son plan, et **Fenêtre › Tâches en arrière-plan** compte les prises en cours (« 2 prises en cours »).
- Quand un lot se termine, un message indique combien de prises sont prêtes (« 2 prises brouillons prêtes ») avec un bouton **Voir** qui ouvre les résultats, et un autre combien ont échoué (« 1 prise en échec »). PotionUI envoie aussi les notifications « Video Producer: take ready » et « Video Producer: take failed » (leur libellé reste en anglais), si bien que vous pouvez quitter la page : les générations continuent sans elle, et les prises sont là à votre retour.
- **Annuler** sur une carte arrête cette prise. **Annuler** dans la barre, ou **Production › Annuler la génération**, arrête toutes les prises en cours (« Génération annulée » ; « Aucune génération en cours. » s’il n’y en a pas). Les minutes GPU qu’elles avaient réservées sont rendues.
- **Réessayer** sur une carte en échec lance une nouvelle prise pour le même plan, avec la même graine, la même qualité et le même moteur. La prise en échec reste dans la liste.

### Profils selon le preset

Le **Profil H3 du projet** (Director IA, onglet **Direction**) dit ce qui guide la génération. Ce qu’un moteur sait faire dépend de son preset, et la page grise les profils qu’il ne sait pas générer.

| Profil | Wan 2.1 / 2.2, LTX-2 / 2.3, LTX-2.5, modèles cloud | MiniMax H3 | MiniMax H3 Fast et VDN |
|---|---|---|---|
| FL2VA | Oui | Oui | Oui |
| Ref2VA | Grisé | Oui | Grisé |
| Hybrid AV | Grisé | Oui | Oui |

- Un profil grisé porte un badge tel que « Ref2VA · Hybrid AV : MiniMax H3 seulement », avec l’explication « Wan 2.1 / 2.2 ne sait pas générer Ref2VA, Hybrid AV : les images de référence (Ref2VA) et le son généré (Hybrid AV) demandent MiniMax H3. » Dans l’onglet **Références**, « Non envoyées avec ce moteur » vous dit que le moteur ignore les références (« Les références ne partent qu’avec le profil Ref2VA sur MiniMax H3 ; Wan 2.1 / 2.2 les ignore. »).
- **FL2VA** utilise les frames liées au plan : une frame de début et une de fin donnent une prise « première et dernière frames », une frame de début seule « première frame », et aucune frame « texte seul », avec l’avertissement ci-dessus.
- **Ref2VA** envoie à MiniMax H3 les références du plan, puis les références globales : au plus 9 images, 3 vidéos et 3 fichiers audio.
- **Hybrid AV** fonctionne comme FL2VA sur MiniMax H3, dont le modèle produit l’image et le son ensemble. La piste qui guide la performance (Atelier avancé) n’est pas encore envoyée (chapitre 17).

## 9. Prises et final

Une prise est une vidéo générée pour un plan. Sa vidéo est une génération PotionUI ordinaire : elle reste dans votre historique de générations (la galerie), même si vous supprimez la prise ici.

- Les brouillons sont faits à la résolution choisie par votre admin (832×480 sauf changement) ou à la plus proche que le moteur propose. La cadence d’une prise est imposée par le preset (Wan 16 i/s, MiniMax H3 24 i/s). La timeline et les exports utilisent la cadence du projet.
- Plusieurs variantes sont faites par plan : A, B, etc. Une nouvelle génération pour le même plan continue avec les lettres libres suivantes (C, D…), séparément pour les brouillons et les finals ; **Réessayer** et **Passer en final** gardent la lettre de la prise dont elles partent. Elles sont listées dans l’inspecteur, onglet **Prises** (en **Finales** et **Brouillons**), et dans Director IA, onglet **Résultats**, regroupées par plan.

### La carte de prise

- La vignette porte la lettre de la prise. Cliquez dessus pour prévisualiser la prise dans le visualiseur (« Prévisualiser la prise A ») ; **Revenir à la séquence** vous ramène.
- La première ligne dit « Brouillon », « Final » ou « Final · agrandi », puis l’état (« En file », « En cours », « Échec », « Annulée ») ou, une fois terminée, la durée. Les lignes suivantes donnent le profil et la façon dont le plan a démarré (« FL2VA · première et dernière frames », « FL2VA · texte seul », « FL2VA · première frame », « Ref2VA · références »), la résolution et, pour un final, la prise dont il vient (« issue de A »), la graine (« Graine 123456 ») et le moteur qui l’a produite (le preset ou le modèle, puis le backend).
- Une prise en file n’affiche que son état (« En file ») au-dessus d’une ligne vide ; une prise en cours de génération affiche l’étape, le pourcentage et une barre de progression. Quand elle échoue, elle affiche la raison que donne PotionUI (en anglais) ou, s’il n’en donne aucune, « La génération a échoué (cuda_oom). » avec le code.
- **Comparer** met la prise à côté d’une seconde dans le visualiseur, toutes deux lues en boucle (« Choisissez une seconde prise à comparer »). **Garder** (l’étoile) et **Rejeter** (le pouce vers le bas) marquent la prise ; cliquez de nouveau pour retirer la marque. L’export signale un plan dont la prise est marquée Rejeter. **Détails de la génération** ouvre la fenêtre de PotionUI sur la génération. **Supprimer** demande « Supprimer cette prise ? » (« La prise A de “Plan 2” quitte la liste. La vidéo reste dans votre historique de générations. »).
- Une capture de cartes de prise, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/takes-cards.png`.
- Sur une prise en cours, **Annuler** l’arrête. Sur une prise en échec, **Réessayer** lance une nouvelle prise.

### Choisir une prise

**Choisir** met la prise sur le plan : elle joue sur la timeline, le plan passe en Brouillon ou en Final, et la carte affiche une coche et **Utilisée**. Une seule prise est choisie par plan. Le premier brouillon qui se termine pour un plan encore « À générer » y est mis pour vous, et un final terminé aussi. Dans le visualiseur, une prise prévisualisée hors montage a **Utiliser cette prise**. **Assembler les prises choisies** (onglet Résultats) met dans le montage toutes les prises choisies ; sans aucune, la page dit « Choisissez d’abord des prises pour les plans. »

### Passer en final

**Passer en final** sur une carte brouillon (aussi le bouton d’une carte du Storyboard, **Passer la prise A en final** dans l’inspecteur, **Plan › Passer la prise en final** et Ctrl+Shift+G) ouvre la fenêtre « Passer en final · Plan 2 · A » avec la ligne « Brouillon en 832×480 · graine 123456 ». Elle propose deux voies :

- **Agrandissement** est la voie par défaut. Le moteur agrandit la prise telle quelle : l’image et le mouvement ne changent pas, et c’est le plus rapide. Les prises de Wan, LTX, MiniMax H3 Fast et VDN et des modèles cloud passent par SeedVR2 (« SeedVR2 agrandit cette prise telle quelle : le plus rapide, le mouvement ne change pas. ») ; une prise du preset MiniMax H3 de base utilise le mode d’agrandissement de son propre preset (« MiniMax H3 agrandit cette prise avec son propre mode d’agrandissement : le mouvement ne change pas. »). Choisissez la **Résolution cible** : 720p, 1080p, 1440p ou 4K (la fenêtre part de la résolution de votre projet), puis cliquez sur « Agrandir en 1080p ».
- **Générer à nouveau en pleine résolution** génère le plan à nouveau à la plus grande résolution du moteur, avec la même graine : « plus lent, le résultat peut légèrement différer. »

Quand aucun agrandisseur ne vous est attribué, la fenêtre indique « Agrandisseur indisponible » (« Aucun agrandisseur ne vous est attribué : demandez à un administrateur d’activer SeedVR2, ou générez à nouveau en pleine résolution. »), les résolutions sont grisées et seul le nouveau rendu est proposé. Une prise du preset MiniMax H3 de base n’a pas besoin de SeedVR2, tant que son preset vous est attribué. Une capture de cette fenêtre, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/make-final.png`.

La nouvelle prise est une prise **Final** (« Final » ou « Final · agrandi ») qui dit de quel brouillon elle vient (« issue de A »). Vous obtenez « Agrandissement en 1080p lancé » ou « Rendu en 1280×720 lancé », le final apparaît dans la liste de cartes quand il se termine, et il est mis sur le plan (« Version finale prête et appliquée au plan »). Un final consomme des minutes GPU comme toute prise et est vérifié par rapport à votre quota.

## 10. Assistant

Le bouton **Assistant**, **Fenêtre › Assistant PotionUI** et Ctrl+J ouvrent le chat PotionUI, en mode **Video Producer**. L’assistant peut :

- écrire l’instruction du plan sélectionné ;
- corriger les contradictions entre la direction globale et les instructions locales ;
- découper votre synopsis en plans ;
- vérifier la continuité entre les plans.

Chaque modification du projet demande votre approbation avant d’être appliquée. L’assistant connaît l’espace où vous êtes, votre sélection, la tête de lecture, la plage, la direction globale, le synopsis et l’état de la production. Il faut que votre admin ait configuré un modèle de langage.

Dans cette version, le bouton, le menu et le raccourci ouvrent déjà le chat PotionUI, tout comme les liens **Demander à l’assistant PotionUI** (bibliothèque de prompts) et **Demander à l’assistant** (atelier Sound design). Les quatre actions ci-dessus arrivent à l’étape 5.

Disponible à partir de l’étape 5.

## 11. Prompts : bibliothèque et compositeur

La fenêtre **Bibliothèque & assistant de prompts** s’ouvre par **Fenêtre › Bibliothèque de prompts**, ou par les liens **Bibliothèque & assistant** placés près d’un texte (dans les champs de la direction globale, dans l’inspecteur pour une instruction locale et dans la fenêtre qui l’édite). Elle écrit dans une cible, indiquée sous son titre : l’un des cinq champs de la direction globale, ou une instruction locale. Ouverte depuis le menu, elle n’a pas de cible et copie le prompt dans le presse-papiers (**Copier le prompt**). La fenêtre a deux onglets, **Bibliothèque** et **Compositeur**, et un lien, **Demander à l’assistant PotionUI**, qui ferme la fenêtre et ouvre le chat PotionUI. Les noms, descriptions et catégories des gabarits et les choix du compositeur existent en français et en anglais et suivent la langue de l’interface ; les textes qu’ils insèrent suivent la langue des prompts du projet (chapitre 15).

- **Bibliothèque.** Cinq bibliothèques, **Intégrée**, **Personnelle**, **Projet**, **Favoris** et **Historique**, et neuf catégories (Cinéma, Caméra, Éclairage, Styles cinématographiques, Dialogue, Photographie, Son, Continuité, À éviter). Cherchez par nom, description ou mot-clé ; l’étoile marque un favori. Chaque gabarit indique les profils H3 auxquels il convient. Un gabarit peut avoir des variables, comme le sujet ou le lieu, que vous remplissez avant de l’insérer. L’**Aperçu modifiable** peut aussi être modifié à la main. **Enregistrer dans Personnelle** garde votre version, et chaque texte inséré va dans **Historique**. Un nouveau projet démarre avec les gabarits intégrés et un gabarit personnel ; **Projet**, **Favoris** et **Historique** sont vides tant que vous n’avez pas mis un gabarit en favori ou inséré un texte.
- **Compositeur.** Construit un prompt à partir de quatre parties, **Mouvement de caméra**, **Éclairage**, **Style cinématographique** et **Dialogue ou intention de jeu**, pour le profil H3 que vous choisissez (il part du profil du projet). Choisissez une option par partie, ou écrivez la vôtre dans **Autre…**, et renseignez le sujet, l’action, le lieu et l’émotion. Le **Prompt final** reste modifiable, et **Recomposer depuis les choix** le ramène à l’état d’origine. **Références nécessaires** indique si la plage a ce que le profil demande. Quand une Control video couvre la plage, la partie caméra est **Imposé par la Control video** et verrouillée.
- **Insérer** écrit le texte dans la cible : **Compléter le texte** l’ajoute au texte existant, **Remplacer** le remplace.

Les trois profils H3 et ce que chacun demande sur la plage :

| Profil | Sens | Il demande | Moteurs |
|---|---|---|---|
| FL2VA | Continuité entre les images de départ et d’arrivée. | Des frames de départ et d’arrivée sur la plage. Sans aucune frame, les plans sont générés à partir du texte seul. | Tous. |
| Ref2VA | Préserver l’identité des références pendant l’action. | Une référence d’identité (personnage, objet). La génération suit vos références. | MiniMax H3 seulement (pas ses variantes Fast et VDN). |
| Hybrid AV | La bande son, le rythme et le dialogue guident l’image. | Une piste audio existante sur la plage (dialogue ou musique). | MiniMax H3, Fast et VDN. |

Le moteur, et non le tableau, a le dernier mot : la page grise un profil que le moteur choisi ne sait pas générer (chapitre 8). Les pistes audio du projet ne sont pas encore envoyées au moteur : MiniMax H3 produit le son lui-même, et la piste qui guide la performance reste simulée (chapitre 17).

Quand une Control video est présente, le mouvement vient du guide.

## 12. Couleur et continuité

Une alerte n’apparaît que lorsque deux plans voisins ne se raccordent pas : « “Plan” est plus clair, plus sombre, plus chaud ou plus froid que le plan précédent ». Elle s’affiche dans Director IA (onglet **Direction**, sous **Points à vérifier**), dans le Storyboard (sous **Continuité**, et par une icône d’alerte sur la carte du plan) et dans l’inspecteur. **Raccorder** corrige en un clic, en ajustant l’exposition et la température sur celles du plan précédent. La mesure est faite sur les vraies vignettes des prises. L’onglet **Couleur** contient aussi le scope de luminance, six préréglages (Original, Lumière dorée, Matin froid, Film 35 mm, Nuit bleue, Doux) et des réglages fins (**Exposition**, **Contraste**, **Saturation**, **Température**), avec **Réinitialiser** et **À tous les plans**. Tant qu’un plan n’a pas d’image, l’onglet indique que la couleur se règle une fois le plan généré.

Dans cette version, la mesure est déjà faite, sur l’image de chaque plan qui en a une. Le projet de départ n’en a pas encore, et le Storyboard indique alors « Aucun raccord à calculer : les plans n’ont pas encore d’image. » Un pourcentage de ressemblance entre deux plans générés peut aussi apparaître dans les alertes (« Identité à vérifier entre … et … (similarité 78 %) ») : il est simulé (chapitre 17). La couleur, elle, est réelle.

Disponible à partir de l’étape 6.

## 13. Audio et sous-titres

L’audio vit dans des pistes, chacune avec un rôle : Dialogue, Musique, Ambiance ou SFX. **Audio › Ajouter une piste audio** et **Audio › Importer un fichier audio…** font entrer des sons ; **Audio › Console de mixage** affiche la console. Dans la console, chaque tranche a un rôle, des effets (**Égaliseur**, **Compresseur**, **Filtre** ; **+ effet** en ajoute un), des envois vers les bus de réverbération et de délai (R et D), un panoramique, un fader (double-cliquez dessus pour revenir à 0 dB), un vumètre, **M** et **S** et un bouton d’automation ; les bus auxiliaires et le **Master** suivent. Les pastilles du haut ne montrent qu’un rôle. **Voix et dialogues…** et les commandes de sound design (**Ambiance…**, **Bruitage…**, **Texture…**, **Impact…**, **Intention musicale…**) ouvrent l’**Atelier Sound design**, qui est simulé (chapitre 17). Le texte d’un dialogue, lui, est réel : il alimente les sous-titres, avec les titres de la timeline.

Les quatre pistes d’un nouveau projet sont vides. **Audio › Importer un fichier audio…** fait entrer vos propres fichiers audio (chapitre 6). La console les joue pour de vrai : les faders, muet et solo, panoramique, égaliseur, compresseur, filtre et envois agissent sur le son que vous entendez, les vumètres le montrent, et les clips de la timeline dessinent la forme d’onde du fichier. Les sons que l’atelier Sound design prépare sont encore synthétisés par votre navigateur (WebAudio).

## 14. Exports

**Fichier › Exporter la vidéo…** ouvre **Exporter et partager**, avec trois onglets :

- **Vidéo.** Choisissez un format, une résolution et l’étendue (**Séquence entière** ou **Plage**), et dites s’il faut ajouter les stems audio. Les formats sont **Fichier maître · ProRes 422**, **Web · H.264 MP4**, **Réseaux sociaux · H.264 vertical** et **Archive · H.265**. L’export réel écrit du H.264 MP4 ou du WebM VP9 ; ProRes 422, H.265 et les stems audio restent simulés et portent le badge.
- **Vers un autre logiciel.** Final Cut Pro (`.fcpxml`), OpenTimelineIO (`.otio`) et EDL CMX 3600 (`.edl`). Ce sont de vrais fichiers.
- **Sous-titres.** Un fichier SRT construit à partir du texte des dialogues et des titres. **Fichier › Exporter les sous-titres…** ouvre cet onglet.

Avant l’export, la fenêtre signale les plans qui ne sont pas encore en version finale, les plans qui utilisent une prise que vous avez marquée **Rejeter** et les contradictions de direction non résolues. Les exports sont écrits dans votre stockage PotionUI, dans un dossier `video_producer/exports/`, et vous les téléchargez depuis la page. Votre admin fixe un budget de taille pour ce dossier, par utilisateur.

Dans cette version, seuls les deux derniers onglets produisent des fichiers. Leur bouton (le mot « Télécharger » suivi du nom du fichier, qui vient du nom du projet) construit le fichier dans votre navigateur et l’enregistre par son intermédiaire : rien n’est écrit dans votre stockage PotionUI. Les chemins de médias à l’intérieur des fichiers Final Cut Pro, OpenTimelineIO et EDL sont fabriqués à partir des noms des médias, ce ne sont pas des chemins de vrais fichiers vidéo, et un plan sans média devient un vide. L’onglet **Vidéo** affiche une barre de progression et se termine par une note disant qu’aucun fichier vidéo n’est écrit à cette étape.

Disponible à partir de l’étape 6.

## 15. Langue

Video Producer existe en anglais et en français. Choisissez **English** ou **Français** dans **Video Producer › Préférences…**, réglage **Langue**, ou cliquez sur le rappel `EN` ou `FR` à gauche de la barre d’état, qui ouvre la même fenêtre. Le changement est immédiat et n’est enregistré que pour vous, sur le serveur ; si l’enregistrement échoue, un message indique que la langue n’a changé que pour cette session. Tant que vous n’avez pas choisi, la page suit la langue de votre navigateur (français s’il est en français, anglais sinon).

La fenêtre **Préférences** a cinq autres réglages : **Langue des prompts** (voir plus bas), **Qualité d’aperçu** (**Meilleures performances**, **Équilibrée** ou **Meilleure qualité**, sans effet pour l’instant), **Magnétisme par défaut**, **Guides de cadrage** et **Raccourcis à une touche** (chapitre 16). Sauf **Langue des prompts**, enregistrée avec le projet, ils valent pour la session en cours et ne sont pas enregistrés.

Ce qui est traduit : les menus, les fenêtres, les boutons, les infobulles, les messages, les noms donnés aux nouveaux éléments (par exemple un nouveau plan ou une nouvelle piste), la bibliothèque de prompts avec ses gabarits, ses catégories et les choix du compositeur, et la façon d’écrire les nombres et les durées. Ce qui n’est jamais traduit, c’est le contenu de votre projet : vos propres textes (synopsis, direction, prompts, noms et titres que vous avez saisis, nom du projet) et le projet de départ, qui est créé une fois et n’est pas traduit ensuite. Les termes du produit comme Director IA, Storyboard, Control video ou FL2VA sont les mêmes dans les deux langues.

### Langue des prompts

Chaque projet a sa propre **Langue des prompts**, anglais ou français. C’est la langue des textes envoyés aux modèles, la direction globale et les instructions locales, et elle ne dépend pas de la langue de l’interface. C’est l’anglais par défaut.

Changez-la dans **Propriétés du projet…** (le réglage dit « Langue de la direction et des prompts envoyés aux modèles. La changer ne réécrit pas les textes existants. ») ou dans **Préférences…** (le réglage dit « S’applique au projet courant »). Elle est enregistrée avec le projet. Un nouveau projet démarre toujours en anglais, quelle que soit la langue de l’interface ou du projet ouvert.

Ce qu’elle change :

- **Le projet de départ.** Sa direction globale et ses instructions locales sont écrites en anglais, même quand l’interface est en français. Son nom, son synopsis, les noms de ses plans, son titre et son marqueur suivent la langue de l’interface.
- **La bibliothèque de prompts.** Le texte que les gabarits intégrés insèrent, leurs variables (le sujet, le lieu, etc.) et les valeurs par défaut de ces variables sont écrits dans la langue des prompts. Les noms, descriptions et catégories des gabarits suivent la langue de l’interface.
- **Le compositeur.** Le **Prompt final** est composé dans la langue des prompts. Les choix sur lesquels vous cliquez gardent la langue de l’interface.
- **Les contrôles de direction.** Les contrôles qui lisent vos textes utilisent les règles de la langue des prompts : les contradictions entre la direction globale et une instruction locale (par exemple une direction qui exclut le néon et une instruction qui en demande), et les instructions de caméra d’une instruction locale qu’une Control video couvre. Un texte écrit dans l’autre langue n’est pas contrôlé.
- **L’assistant.** Disponible à partir de l’étape 5 : il écrit les instructions locales dans la langue des prompts.

Ce qu’elle ne change jamais : rien de ce que vous avez saisi n’est traduit, et changer le réglage ne réécrit aucun texte existant. Réglez la langue avant d’écrire, ou réécrivez les textes vous-même.

## 16. Raccourcis clavier

Le tableau donne les raccourcis pour Windows et Linux. Sur un Mac, lisez ⌘ pour Ctrl, ⌥ pour Alt et ⇧ pour Shift ; les menus et les infobulles affichent la notation de votre système, et le panneau latéral se fait avec ⌃⌘1 (Contrôle et Commande). **Rechercher une commande…** (Ctrl+K) trouve toutes les commandes, et **Raccourcis clavier** (Ctrl+Alt+K) liste celles qui ont un raccourci.

| Raccourci | Action |
|---|---|
| Ctrl+K | Rechercher une commande… |
| Ctrl+Alt+K | Raccourcis clavier |
| Ctrl+, | Préférences… |
| Échap | Fermer, dans cet ordre : la recherche de commande, la fenêtre ouverte, le menu ouvert, un aperçu ou une comparaison de prises ; sinon désélectionner |
| Ctrl+Z, Ctrl+Shift+Z | Annuler, Rétablir |
| Ctrl+S | Enregistrer |
| Ctrl+O | Ouvrir… |
| Ctrl+I | Importer des fichiers… |
| Ctrl+Alt+J | Propriétés du projet… |
| Ctrl+E, Ctrl+Shift+E | Exporter la vidéo…, Exporter vers un autre logiciel… |
| Ctrl+G | Générer la sélection |
| Ctrl+Alt+G | Ajouter la sélection à la file |
| Ctrl+Shift+G | Passer la prise en final |
| Ctrl+J | Assistant PotionUI (ouvre le chat) |
| Ctrl+Alt+1 | Panneau latéral |
| Espace | Lecture / pause |
| Ctrl+B | Couper à la tête de lecture |
| Ctrl+D | Dupliquer |
| Retour arrière, Suppr | Supprimer |
| A, R, B | Outil Sélection, Outil Plage, Outil Lame |
| I, O | Définir le point d’entrée, Définir le point de sortie |
| M | Ajouter un marqueur |
| N | Magnétisme |
| Flèche gauche, Flèche droite | Déplacer la tête de lecture de 1/25 s (1 s avec Shift) |
| Flèche gauche, Flèche droite (Storyboard) | Sélectionner le plan précédent ou suivant |
| Home | Aller au début |

Les raccourcis à une lettre (A, R, B, I, O, M et N) peuvent être désactivés dans **Video Producer › Préférences…**, réglage **Raccourcis à une touche**, activé par défaut. Espace, Retour arrière, Suppr, les flèches et Home n’en dépendent pas.

Quand les raccourcis fonctionnent :

- Seulement quand le focus est sur la page et pas dans un champ de texte. Avec un champ de texte actif, une fenêtre ouverte (sélecteur ou confirmation PotionUI compris) ou la recherche de commande ouverte, les autres raccourcis sont inactifs ; Échap, Ctrl+K et Ctrl+Alt+K agissent toujours. Tant que le chat PotionUI est ouvert, les raccourcis de la page sont inactifs.
- Les menus et la fenêtre **Raccourcis clavier** affichent aussi d’autres combinaisons, par exemple Ctrl+N, Ctrl+C, Ctrl+V, Ctrl+F ou Ctrl+1 à Ctrl+5 pour les espaces. Elles ne sont pas actives dans cette version : utilisez le menu, les boutons ou le sélecteur d’espaces.

## 17. Ce qui est simulé

Certaines parties gardent leur interface mais ne font pas encore la vraie chose. Elles portent un badge gris pointillé, **Simulé**, jamais jaune : le jaune est réservé aux vrais points à vérifier. **Aide › Fonctions simulées** ouvre la liste. Le même badge gris marque aussi ce que le moteur choisi ne sait pas faire (un profil grisé, « Non envoyées avec ce moteur » sur les références, « Non transmis à ce moteur » sur les réglages de l’atelier, « Agrandisseur indisponible » ; chapitres 8 et 9).

Le badge **Simulé** apparaît dans l’en-tête des fenêtres **Référencer un fichier Gaussian Splat** et **Atelier Sound design** (intitulé **Voix et dialogues** pour une voix) ; à côté des formats **Fichier maître · ProRes 422** et **Archive · H.265**, à côté des stems audio et dans le pied de l’onglet **Vidéo** de la fenêtre d’export ; sur le bouton d’automation des tranches de la console ; sur la **Scène d’essai** et sur l’aperçu d’un fichier Gaussian Splat dans la scène 3D ; et sur une prise faite par une version antérieure du projet, sur sa carte (« Prise simulée d’une version antérieure du projet : lecture seule. ») et dans le visualiseur (« Prise finale · IA simulée », « Brouillon 720p · IA simulée »). Les prises de la génération réelle ne le portent jamais. Quelques notifications sont signalées de la même façon.

Ce qui fonctionne déjà dans cette version : la génération elle-même (les moteurs activés par votre admin, l’estimation, les prises avec leur progression, l’annulation et la reprise, les finals par agrandissement ou nouveau rendu, le quota et les notifications), les projets enregistrés, **Fichier › Ouvrir…**, **Fichier › Historique des versions…** et **Fichier › Nouveau projet…**, l’import de vos images, vidéos et fichiers audio avec leurs vignettes et leur lecture, le montage sur la timeline (ajustement des plans, fondus, coupe, magnétisme, plage, marqueurs, annuler et rétablir), la sélection et l’inspecteur, le Storyboard, la bibliothèque de prompts et le compositeur, le contrôle des contradictions de direction, le raccord de couleur, la caméra, les trajectoires et les positions clés de la scène 3D, la console de mixage qui joue vos fichiers audio, et les fichiers Final Cut Pro, OpenTimelineIO, EDL et SRT, qui sont de vrais fichiers.

La fenêtre **Fonctions simulées** liste huit éléments. Pour chacun, le tableau dit ce qu’il fait dans cette version et ce qu’il devient quand toutes les étapes sont livrées.

| Élément de la fenêtre | Dans cette version | Quand toutes les étapes sont livrées |
|---|---|---|
| **Modes de rendu 3D et réglages du moteur** | Les modes de sortie « Rendu 3D » et « Rendu 3D + IA » ne lancent rien. Les réglages grisés dans l’atelier avancé ne sont pas transmis au moteur : la graine (chaque prise tire la sienne), la résolution finale (le final prend la plus grande résolution du moteur), les étapes, le CFG, les LoRA, les fenêtres, la cohérence, les post-traitements et le pilote audio Hybrid AV ; pas plus que les Control video et les poids du Hybrid builder. Les prises faites par les versions antérieures gardent leur vignette numérotée. | Reste simulé. La génération IA elle-même est réelle : voyez les chapitres 8 et 9. |
| **Découpage du synopsis** | Une phrase devient un plan. | L’assistant propose le découpage. Disponible à partir de l’étape 5. |
| **Contrôle d’identité** | La similarité entre plans est simulée. Le contrôle de couleur, lui, analyse réellement les images. | Le raccord de couleur est mesuré sur les vraies vignettes des prises (à partir de l’étape 6). Le pourcentage de ressemblance reste simulé, car aucune mesure d’identité n’est offerte aux plugins. |
| **Rendu vidéo** | Aucun fichier vidéo n’est écrit. Les exports Final Cut, OTIO, EDL et SRT produisent de vrais fichiers. | Des vidéos H.264 MP4 ou WebM VP9 assemblées avec ffmpeg et écrites dans votre stockage. ProRes 422, H.265 et stems audio restent simulés : le convertisseur vidéo de PotionUI n’écrit que du H.264 MP4 ou du WebM VP9, et aucun rendu audio par rôle n’existe. Disponible à partir de l’étape 6. |
| **Gaussian Splat** | Le fichier référencé n’est pas chargé ; la scène d’essai est un nuage de points généré. | Reste simulé : la scène reste un aperçu de points en 2D et les fichiers Gaussian Splat sont référencés, pas chargés. |
| **Control video** | Le calcul du guide depuis la scène 3D est simulé. | Reste simulé : la vidéo de guide n’est pas rendue depuis la scène, une Control video importée n’est envoyée à aucun moteur et la capture 3D n’est pas rendue depuis la scène. Les modes de production **Rendu 3D** et **Rendu 3D + IA** dépendent de ce guide et restent simulés. |
| **Voix et sound design** | La préparation est simulée ; la pré-écoute est une synthèse simple. | Reste simulé : personnage, timbre et texte ne produisent pas de parole, la synchronisation labiale n’a pas d’étape séparée (MiniMax H3 fait image et son en une passe) et aucun preset ne prépare ambiances, bruitages, textures, impacts ou musique pour l’atelier. Le texte des dialogues alimente bien les sous-titres. |
| **Audio du montage** | Les fichiers audio que vous importez sont lus pour de vrai par la console : faders, muet et solo, panoramique, égaliseur, compresseur, envois et vumètres agissent dessus. Les sons préparés par l’atelier Sound design sont synthétisés en temps réel (WebAudio). | Reste simulé pour les sons de l’atelier, car aucun preset ne les prépare, et pour les courbes d’automation : le bouton d’automation ne change qu’un mode, aucune courbe n’est enregistrée. |

La fenêtre ne liste pas tous les réglages de l’**Atelier avancé** que le moteur n’utilise pas : cohérence entre fenêtres, verrouillage de l’identité des personnages, priorité au guide de mouvement, les fenêtres de génération avec leur longueur et leur chevauchement, la résolution finale, la graine, les étapes, le guidage (CFG), les LoRAs, la piste qui guide la performance, la synchronisation labiale, le rythme du montage, le décalage audio / image, le nommage des résultats, les post-traitements et l’insertion automatique de la variante A. Ils restent dans le projet, mais ils ne sont pas envoyés au moteur et ne pilotent aucune génération : un preset n’expose que les contrôles qu’il déclare ; MiniMax H3, par exemple, n’a ni guidage ni prompt négatif. L’atelier les grise et marque chacun du badge « Non transmis à ce moteur » (survolez-le : « Le Video Director construit la requête à partir des plans, de la direction, des frames et des références ; ce réglage reste dans le projet mais ne change pas les prises. »). Les **Variantes par fenêtre** restent actives. Les poids du Hybrid builder et ses profils enregistrés, et le guidage d’une Control video, ne sont pas envoyés non plus, mais ils ne sont pas grisés. Ce qui compte, c’est le moteur, la qualité, les variantes et ce qui est dans votre projet : la direction, les instructions locales, les frames et les références. La graine d’une prise est tirée par le serveur et affichée sur sa carte, et les résolutions suivent les règles du brouillon et du final du chapitre 8.

L’assistant, lui, n’est pas simulé : c’est le chat PotionUI en mode Video Producer, qui écrit les instructions de plan, corrige les contradictions avec la direction globale, découpe un synopsis en plans et vérifie la continuité, et vous approuvez chaque changement avant qu’il touche le projet (disponible à partir de l’étape 5).

## 18. Dépannage

- **La barre Production n’affiche aucun moteur.** Le menu indique « Aucun moteur ». Votre admin n’a pas terminé la mise en place : un moteur, un preset vidéo qui vous est attribué, ou un modèle vidéo activé chez le fournisseur cloud. Demandez-lui d’ouvrir Admin → Plugins → Video Producer.
- **L’estimation affiche « — » pour le temps.** Rien n’a encore été mesuré pour ce preset, ce moteur et cette résolution (la calibration est vide). Elle se remplit après quelques générations.
- **« Passera par la RAM de l’hôte, plus lent. »** L’estimation de mémoire dépasse celle du GPU. La génération n’est pas bloquée. Si le serveur manque de mémoire libre pour cela, le moteur refuse de démarrer et la prise échoue (`host_ram_oom`).
- **Le quota est épuisé.** **Générer la sélection** dit « Quota GPU dépassé » jusqu’au mois suivant ou jusqu’à ce que votre admin relève la limite de votre plan. Les générations en cours ne sont pas arrêtées, et une prise qui échoue ou qui est annulée rend ses minutes. Les premières prises d’un preset comptent 10 secondes de GPU par seconde de vidéo, ce qui peut paraître généreux tant que les durées réelles n’ont pas été mesurées.
- **Générer la sélection est désactivé.** Lisez le message de la barre : pas de plage, ni direction ni instruction locale, une instruction vide, un mode 3D sans plan 3D, aucun moteur, un preset qui n’est pas le vôtre, un profil que le moteur ne sait pas générer, des modèles à installer, un modèle cloud à choisir, ou le quota.
- **« Modèles à installer pour ce preset : … ».** Votre admin n’a pas téléchargé les fichiers de modèle dont ce preset a besoin. Demandez-les-lui.
- **Un avertissement dit que les plans seront générés à partir du texte seul.** Le profil FL2VA n’a aucune frame liée au plan. Ajoutez une frame de départ ou d’arrivée, ou choisissez un autre profil H3 ; la génération n’est pas bloquée.
- **Une prise reste En file.** Votre admin limite le nombre de générations que vous pouvez avoir en cours en même temps : la prise démarre d’elle-même quand l’une des vôtres se termine. Si elle reste En file alors que rien de vous ne tourne, prévenez votre admin.
- **Une prise a échoué.** La carte affiche la raison que donne PotionUI (en anglais) ou, s’il n’en donne aucune, « La génération a échoué » suivi d’un code. **Réessayer** lance une nouvelle prise pour le même plan, avec la même graine. Causes fréquentes : le GPU a manqué de mémoire (`cuda_oom` : essayez un brouillon, un plan plus court ou un autre moteur) ; un fichier de modèle manque sur le serveur (`missing_model_file` : demandez à votre admin de le télécharger de nouveau) ; le serveur a manqué de mémoire en faisant passer le modèle par sa RAM (`host_ram_oom`). Si PotionUI a redémarré pendant la génération, la prise est marquée en échec et la génération ne peut pas reprendre : utilisez **Réessayer**.
- **« Agrandisseur indisponible » dans Passer en final.** Aucun agrandisseur ne vous est attribué : SeedVR2 agrandit les prises de Wan, LTX, MiniMax H3 Fast et VDN et des modèles cloud. Utilisez **Générer à nouveau en pleine résolution**, ou interrogez votre admin sur SeedVR2.
- **Les références sont ignorées avec MiniMax H3.** Demandez à votre admin de vérifier le fichier de modèle choisi pour le mode Références. Le moteur ignore les références d’un profil autre que Ref2VA, et de tout autre preset.
- **J’ai fermé la page pendant une génération.** Les prises continuent ; rouvrez le projet pour les retrouver. Les notifications vous disent quand elles se terminent.
- **Un export échoue.** Interrogez votre admin sur ffmpeg, ou libérez de la place dans vos exports : le dossier a un budget de taille.
- **La barre projet indique « Non enregistré — réessayer ».** Le dernier enregistrement a échoué : la connexion a été coupée, ou le serveur a refusé le projet. Un message dit lequel. Cliquez sur l’état d’enregistrement ou sur le bouton **Réessayer** du message pour réessayer. Vos modifications restent dans la page et la modification suivante réessaie aussi. Tant qu’un enregistrement ne passe pas, ouvrir un autre projet ou restaurer une version demande de confirmer avant d’abandonner ces modifications. Si le message dit que le contenu a été refusé ou que le projet est trop volumineux, voyez votre admin : recharger la page ferait perdre les modifications non enregistrées.
- **« Projet rechargé : il a été modifié ailleurs ».** Le projet a été enregistré depuis un autre onglet, une autre fenêtre ou un autre appareil après son ouverture chez vous, alors la page a chargé la version enregistrée. Les modifications que vous n’aviez pas enregistrées dans cette page sont perdues. Travaillez sur un projet à un seul endroit à la fois ; **Fichier › Historique des versions…** ramène un état antérieur.
- **« Ce projet a été supprimé ailleurs ».** Le projet a été supprimé depuis un autre onglet ou un autre appareil pendant qu’il était ouvert ici. La page a ouvert votre projet modifié le plus récemment, ou créé le projet de départ. Les modifications que vous n’aviez pas enregistrées sont perdues.
- **Un média ne s’affiche pas ou ne se lit pas.** Son fichier n’est plus disponible dans votre bibliothèque ou votre galerie PotionUI. Importez-le à nouveau. Une prise dont vous avez supprimé la génération de la galerie ne se lit plus non plus.
- **« 1 fichier n’a pas pu être importé » (ou « N fichiers n’ont pas pu être importés »).** Le fichier n’est plus disponible dans la bibliothèque ou la galerie, ou son type n’est pas accepté par la fenêtre : images et vidéos pour **Importer des fichiers…** et **Depuis la galerie PotionUI**, audio pour **Importer un fichier audio…**.

Les exports à partir de l’étape 6.

## 19. Glossaire

| Français | English | Sens |
|---|---|---|
| plan | shot | Un morceau du film, une génération. |
| prise | take | Une version générée d’un plan : une vraie vidéo produite par le moteur choisi. |
| brouillon | draft | Une prise rapide, en résolution réduite, pour juger le mouvement et le cadrage. |
| final | final | La prise retenue, agrandie (agrandissement) ou générée à nouveau à la plus grande résolution (nouveau rendu). |
| moteur | engine | Ce qui produit les prises : un preset vidéo sur le matériel de votre admin, ou un modèle cloud. |
| variante | variant | Une des prises (A, B, …) faites pour un même plan en une génération. |
| graine | seed | Le nombre qui fixe le hasard d’une prise ; la même graine donne une prise semblable. |
| calibration | calibration | Les durées réelles de vos générations passées, gardées par preset, moteur et résolution, que l’estimation utilise pour son temps ; elle affiche « — » tant qu’il n’y en a pas. |
| raccord | match | Faire se ressembler deux plans voisins (couleur) ou garder la même identité. |
| fondu | fade | Un début ou une fin progressive d’un clip. |
| tête de lecture | playhead | La position courante sur la timeline. |
| plage | range | Une partie de la timeline entre un point d’entrée et un point de sortie. |
| direction globale | global direction | Le texte qui guide toutes les générations. |
| langue des prompts | prompt language | La langue de la direction globale et des instructions locales d’un projet, anglais ou français. |
| version | version | Un état enregistré du projet ; **Historique des versions…** les liste et en restaure une. |
| instruction locale | shot prompt | Le texte d’un plan ; il complète la direction globale. |
| Control video | Control video | Une vidéo de guide qui impose le mouvement. |
| profil H3 | H3 profile | FL2VA, Ref2VA ou Hybrid AV : ce qui guide la génération. |
