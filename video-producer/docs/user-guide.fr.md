# Video Producer : guide utilisateur

English: [Video Producer: user guide](/docs?doc=plugin/video-producer/user-guide) (file `docs/user-guide.md`).

Ce guide explique comment réaliser un court film avec Video Producer. Les libellés de l’interface sont écrits en **gras**. L’interface est complète, en anglais et en français. Vos projets sont enregistrés au fil de votre travail, vos médias sont importés depuis PotionUI, et les prises et les finals sont de vraies vidéos (chapitres 8 et 9). L’assistant PotionUI a son propre mode (chapitre 10), les plans sont raccordés entre eux (chapitre 12) et la livraison est réelle : des vidéos pour le web et pour les réseaux sociaux, des fichiers pour un autre logiciel et des sous-titres (chapitre 14). Quelques fonctions sont simulées et signalées comme telles (chapitre 17). Le guide d’administration est une page distincte que seuls les admins voient.

## 1. Ce qu’est Video Producer

Video Producer est un plugin PotionUI de montage audiovisuel, de génération de séquences par IA, de direction artistique, de création sonore et de recadrage depuis la 3D, dans un même espace. Vous écrivez un synopsis, vous le découpez en plans, vous générez des prises brouillon rapides, vous choisissez la meilleure, vous la passez en final, puis vous montez, raccordez les couleurs, mixez et livrez. Il s’ouvre depuis l’entrée **Video Producer** de la barre latérale.

Avant de commencer :

- Un admin doit avoir préparé au moins un moteur (ce poste, un serveur d’atelier ou un modèle cloud) et au moins un preset vidéo qui vous est attribué. Si la barre Production n’affiche aucun moteur, voyez le chapitre 18.
- Votre admin règle aussi la résolution des brouillons, le nombre de générations que vous pouvez avoir en cours en même temps, et peut limiter les minutes GPU que vous pouvez utiliser par mois.
- La génération est réelle : les prises sont des vidéos produites par les machines ou le compte cloud de votre admin, et elles prennent du temps. L’estimation de la barre Production vous dit à quoi vous attendre avant de commencer (chapitre 8). À titre de mesure, sur une carte graphique de 12 Go, un brouillon de 5 secondes a pris environ 6 à 7,5 minutes avec les presets nommés (12 GB) et environ 26 minutes avec Wan, et un final par agrandissement en 1080p a pris plus de deux heures.
- La machine de votre admin décide de ce que vous pouvez utiliser. Un preset dont le nom se termine par une taille de carte est réglé pour une carte graphique de cette taille, et le menu des moteurs ajoute la mémoire ordinaire (RAM) dont le serveur a besoin (chapitre 8). Sur une carte de 8 Go, choisissez **Wan 2.1 T2V 1.3B (8 GB) · 32 GB RAM** ou **Wan 2.2 TI2V 5B (8 GB) · 32 GB RAM** : ils font des clips 480p de 5 secondes au plus à partir du seul texte. Sur une carte de 12 Go, choisissez **MiniMax H3 (12 GB) · 64 GB RAM** ou **MiniMax H3 Fast (12 GB) · 64 GB RAM** : les autres presets MiniMax H3 sont faits pour des cartes plus grosses (celui en Fast a manqué de mémoire sur une carte de 12 Go lors de nos essais). Demandez à votre admin de quelle carte il dispose.
- Livrer un fichier vidéo demande ffmpeg sur votre serveur PotionUI. Si la fenêtre d’export dit que ffmpeg est absent, demandez à votre admin (chapitres 14 et 18). Les fichiers pour un autre logiciel et les sous-titres n’en ont pas besoin.
- L’assistant a besoin d’un modèle de langage que votre admin a configuré dans PotionUI et qui vous est attribué (chapitre 10). Demandez à votre admin de connecter un serveur de modèle local réglé pour l’assistant (le `llama-server` de llama.cpp ou Ollama) ou un fournisseur en ligne : le modèle intégré à PotionUI a manqué de mémoire ou n’a pas su appeler les outils sur une carte graphique de 12 Go lors de nos essais. Tout le reste fonctionne sans lui.
- Le modèle MiniMax H3 (les entrées **MiniMax H3** du menu des moteurs) est sous une licence qui exclut son usage, et tout ce qu’il génère, dans l’Union européenne, au Royaume-Uni, aux États-Unis et en Corée du Sud sans autorisation individuelle de MiniMax, et qui demande qu’un produit commercial affiche « MiniMax H3 » de façon visible. Demandez à votre admin avant de l’utiliser. Video Producer ne vérifie rien de tout cela à votre place.

L’interface est en anglais par défaut et existe aussi en français (chapitre 15).

La première fois que vous ouvrez la page, elle crée un projet de départ, « Aube sur le port » (« Dawn at the harbour » en anglais), et l’ouvre. Il contient un synopsis, la direction globale en cinq champs, cinq plans de 5 secondes encore à générer, chacun avec son instruction locale (le port endormi, les mains du pêcheur, le départ, les goélands, vers le large), un titre, un marqueur nommé « Départ » et quatre pistes audio vides. Il n’a ni média, ni prise, ni référence, ni scène 3D. Son nom, son synopsis, les noms de ses plans, son titre et son marqueur sont écrits dans la langue de l’interface ; sa direction globale et ses instructions locales sont écrites dans la langue des prompts du projet, l’anglais par défaut (chapitre 15). Parcourez-y tout le chemin, ou partez d’un projet vide avec **Fichier › Nouveau projet…**. Aux visites suivantes, la page ouvre le projet que vous avez utilisé en dernier (chapitre 5).

## 2. Le parcours en huit étapes

**Aide › Prise en main** montre le même parcours sous forme de liste sur laquelle vous pouvez cliquer. Les huit étapes :

1. **Créer un projet.** **Fichier › Nouveau projet…** (ou **Fichier › Ouvrir…** pour un projet existant). Dans **Propriétés du projet…** vous réglez le nom, le format (16:9, 2.39:1, 9:16, 1:1 ou 4:5), la résolution (720p, 1080p ou 4K) et la cadence (24, 25 ou 30 i/s). Résultat : un projet vide, enregistré au fil de votre travail.
2. **Définir la direction globale.** Dans l’espace **Director IA**, onglet **Direction** : univers et intention, personnages et identité, direction photographique, palette et éclairage, rythme et continuité. Résultat : un texte qui guide toutes les générations.
3. **Ajouter les références.** Dans **Director IA**, onglet **Références** : identités, décors et guides de mouvement. Résultat : ce qui doit rester identique d’un plan à l’autre.
4. **Découper le film en plans.** Dans l’espace **Storyboard** : écrivez le synopsis, puis cliquez sur **Proposer un découpage** (une phrase devient un plan) ou demandez à l’assistant de le découper (chapitre 10), gardez les plans voulus et ajustez leurs instructions locales. Résultat : une rangée de cartes de plans.
5. **Générer des brouillons.** Dans la barre Production, choisissez le **Moteur de génération**, qualité **Brouillon**, puis **Générer la sélection** (Ctrl+G). L’estimation indique le temps, la mémoire et le quota. Résultat : de vraies prises brouillon A, B, etc., produites par le moteur choisi.
6. **Choisir et passer en final.** Dans l’inspecteur, onglet **Prises** : comparez les prises, étiquetez **Candidate** celles qui valent d’être gardées et **Rejeter** les autres, cliquez sur **Finale** pour celle que le plan doit jouer, puis sur **Passer en final** pour l’obtenir en pleine résolution. Résultat : le plan passe de Brouillon à Final.
7. **Monter, raccorder et mixer.** Fondus sur les clips, raccord de couleur dans l’onglet **Couleur** de l’inspecteur, images de raccord entre les plans (chapitre 12), console dans **Mixage**. Résultat : une séquence terminée.
8. **Préparer la livraison.** **Fichier › Exporter la vidéo…**, **Exporter vers un autre logiciel…** ou **Exporter les sous-titres…**. Résultat : une vidéo dans votre bibliothèque et des fichiers à télécharger.

Les huit étapes fonctionnent pour de vrai, et vos projets sont enregistrés au fil de votre travail (chapitre 5). La page ouvre le projet que vous avez utilisé en dernier, ou le projet de départ la première fois (chapitre 1). **Nouveau projet…** démarre un projet vide, « Projet sans titre », et l’ajoute à vos projets. Les brouillons et les finals sont de vraies vidéos produites par les moteurs de votre admin. La livraison est réelle pour les vidéos web et réseaux sociaux et pour les fichiers pour un autre logiciel (chapitre 14) ; le fichier maître, l’archive et les stems audio de la fenêtre d’export sont simulés (chapitre 17).

## 3. L’écran

La page compte cinq niveaux de commandes, du plus large au plus local, autour d’un panneau de gauche, d’une zone centrale, de l’inspecteur et de la timeline :

- **Barre de menus.** Dix menus, dans cet ordre : **Video Producer**, **Fichier**, **Édition**, **Montage**, **Plan**, **Production**, **Audio**, **Présentation**, **Fenêtre**, **Aide**. Le menu **Video Producer** contient **À propos de Video Producer**, **Préférences…**, **Raccourcis clavier** et **Rechercher une commande…**. Un menu n’affiche « … » que si la commande ouvre une fenêtre qui demande une saisie, et une coche devant un état activé.
- **Barre projet.** À gauche, le bouton qui affiche ou masque le panneau latéral, le nom du projet (cliquez dessus pour renommer le projet) et son état d’enregistrement (« Enregistrement… », « Enregistré à » et l’heure, « Modifié · cliquer pour enregistrer » ou « Non enregistré — réessayer » ; chapitre 5). Au milieu, le sélecteur d’espaces : **Médias**, **Lecture**, **Director IA**, **Storyboard**, **Mixage**. À droite, **Importer** (un menu avec **Depuis la bibliothèque…** et **Depuis l’ordinateur…**, chapitre 6), **Exporter**, **Assistant** (il ouvre le chat PotionUI, chapitre 10), un bouton de recherche des commandes et le bouton qui affiche ou masque l’inspecteur.
- **Barre Production.** Elle cible ce qu’il faut générer et porte le seul bouton principal de la page, **Générer la sélection** (chapitre 8).
- **En-têtes de zone et barre d’outils de la timeline.** Un titre et des compteurs à gauche, de petites icônes à droite.
- **Contenu.** De petits boutons qui apparaissent au survol ou à la sélection.

Une règle à retenir : toutes les autres entrées (Storyboard, panneau latéral, Director IA) ne font que cibler ce qu’il faut générer ; c’est la barre Production qui agit.

Les dix menus regroupent toutes les commandes de la page. La recherche de commande (**Rechercher une commande…**, Ctrl+K) les trouve par leur nom, indique leur menu et leur raccourci, et lance la commande avec Entrée.

| Menu | Ce qu’il contient |
|---|---|
| **Video Producer** | À propos, Préférences, Raccourcis clavier, recherche de commande. |
| **Fichier** | Nouveau projet, Ouvrir, Enregistrer, Historique des versions, Importer depuis la bibliothèque, Importer depuis l’ordinateur, Depuis la galerie PotionUI, Propriétés du projet, les trois exports. |
| **Édition** | Annuler, Rétablir, Copier, Coller, Dupliquer, Supprimer, Rechercher un média. |
| **Montage** | Les trois outils, Couper à la tête de lecture, les ajustements du début et de la fin, Modifier la durée, points d’entrée et de sortie, Effacer la plage, Ajouter un marqueur, Ajouter un titre, Fondus d’entrée et de sortie. |
| **Plan** | Nouveau plan, Informations, Afficher la source, Prises du plan, Éditeur de plan, Recadrer depuis la 3D, Passer la prise en final, Couleur du plan, Raccorder la couleur au plan précédent, Favori, Rejeter, Retirer la marque. |
| **Production** | Direction globale, Découper le synopsis en plans, Contrôle de continuité, Générer la sélection, Qualité brouillon et finale, la file de génération, Annuler la génération, Résultats et prises, Assembler les prises choisies, Modifier le moteur. |
| **Audio** | Ajouter une piste audio, Importer un son de la bibliothèque, Importer un son depuis l’ordinateur, Console de mixage, Voix et dialogues et l’atelier Sound design. |
| **Présentation** | Lecture, boucle, plein écran, guides de cadrage, Comparer les prises, Scope de luminance, Indicateurs audio, zoom de la timeline, Magnétisme. |
| **Fenêtre** | Les cinq espaces, les espaces de références, Panneau latéral, Inspecteur, Assistant PotionUI, Bibliothèque de prompts, Index de la timeline, Tâches en arrière-plan. |
| **Aide** | Prise en main, Raccourcis clavier, Rechercher une fonctionnalité, Fonctions simulées. |

### Les zones de la page

- **Panneau de gauche.** Il change avec l’espace (chapitre 4) ; **Lecture** n’en a pas. Affichez-le ou masquez-le avec le premier bouton de la barre projet ou avec Ctrl+Alt+1.
- **Centre.** Le visualiseur, le storyboard ou la planche de références, selon l’espace.
- **Inspecteur.** À droite. Il suit la sélection (chapitre 7). Il démarre masqué quand la fenêtre fait moins de 1360 pixels de large : ouvrez-le avec le dernier bouton de la barre projet, ou sélectionnez quelque chose, ce qui l’ouvre.
- **Timeline.** En bas. Dans **Mixage**, la console de mixage prend sa place et un bouton ramène la timeline ; dans **Lecture**, elle reste sous le visualiseur, sans la barre Production. Glissez la fine ligne au-dessus de la barre Production (au-dessus de la timeline dans **Lecture**) pour lui donner plus ou moins de hauteur.
- **Barre d’état.** Tout en bas, de gauche à droite : le rappel de la langue (`EN` ou `FR` ; cliquez dessus pour ouvrir les Préférences), le nombre de plans avec la durée, la résolution et le format d’image, l’outil actif, la sélection, la plage. À droite : le nombre de points de direction à vérifier (cliquez dessus pour ouvrir l’onglet **Direction**), le nombre de prises dans la file de génération (cliquez dessus pour ouvrir l’onglet **File**), le magnétisme et, si votre admin vous a fixé une limite, votre **Quota GPU**, les minutes utilisées ce mois-ci rapportées à cette limite (les fournisseurs cloud sont facturés à part).

Le visualiseur a sa propre barre de transport : volume de contrôle, retour au début, image précédente et suivante, lecture, boucle, le timecode, guides de cadrage, format d’image, résolution et plein écran. Quand vous prévisualisez une prise, une comparaison ou un média source, une pastille en haut du visualiseur vous ramène à la séquence avec **Revenir à la séquence**.

La timeline a une barre d’outils et une rangée par type d’élément. La barre d’outils contient **Annuler** et **Rétablir**, les trois outils (**Outil Sélection**, **Outil Plage**, **Outil Lame**), **Couper à la tête de lecture**, **Dupliquer**, **Supprimer**, le menu **Ajouter** (**Prompt**, **Frame de référence**, **Titre**, **Marqueur**, **Piste audio**), **Magnétisme**, le zoom et **Ajuster**. Les rangées sont **Titres**, **Prompts**, **Frames**, **V1 · Vidéo** et une rangée par piste audio, nommées **A1**, **A2**… de haut en bas. **V1** et chaque piste audio ont **M** (muet) et **S** (solo) dans leur en-tête (chapitre 13). Cliquez sur le nom d’une piste audio pour la sélectionner ; clic droit dessus, ou touche Menu ou Maj+F10, pour son menu : **Réglages de la piste**, **Ajouter une piste audio** et **Supprimer la piste…**. Un plan dont le média est une vidéo montre un haut-parleur en bas à gauche de son bloc au survol : cliquez dessus pour couper le son de ce plan ; il reste affiché, barré, tant que le plan est muet. Cliquez sur la règle pour déplacer la tête de lecture ; avec l’outil Plage, ou en glissant avec Alt enfoncée, tracez une plage. Glissez un plan pour changer son ordre, glissez ses bords pour le raccourcir ou le rallonger (les plans suivants suivent), glissez les poignées blanches en haut d’un clip pour régler ses fondus, glissez un clip audio vers une autre piste. Les poignées d’ajustement et de fondu sont des poignées pour la souris ; au clavier, utilisez **Montage › Ajuster le début à la tête**, **Ajuster la fin à la tête** et **Fondus d’entrée et de sortie**, ou les champs **Durée et source** et **Fondus** de l’inspecteur (chapitre 7). Ctrl et la molette zooment. Double-cliquez sur un endroit vide de la rangée Prompts ou Frames pour y créer un élément.

## 4. Les espaces de travail

Chaque espace change le panneau de gauche et le centre. L’inspecteur, à droite, suit votre sélection dans tous, sauf **Lecture**, qui ne garde que le visualiseur. **Fenêtre › Index de la timeline** liste les prompts, frames et marqueurs avec leur position, et **Fenêtre › Tâches en arrière-plan** montre la génération en cours et la file.

### Médias

Les médias du projet dans un seul panneau. Un nouveau projet n’en a aucun : le panneau indique « Aucun média dans ce projet. » et propose **Bibliothèque** et **Depuis l’ordinateur**, comme les deux boutons d’import de son en-tête et le menu **Importer** de la barre projet ; vous pouvez aussi y déposer des fichiers. Le chapitre 6 explique comment faire entrer vos images, vidéos et fichiers audio. Filtrez avec les pastilles de collections (**Toutes**, **Images**, **Vidéos**, **Audio**, **Générés**), cherchez par nom sans vous soucier des accents, double-cliquez pour prévisualiser, glissez vers la timeline. Pour un élément sélectionné, le panneau indique sa durée, son format, sa collection et son origine, et propose **Prévisualiser**, **Au montage** et, pour les images et les vidéos, **Utiliser comme frame à la tête de lecture**. Le centre est le visualiseur.

### Lecture

Le montage de V1 lu dans un grand visualiseur, avec la timeline en dessous. Lecture n’a ni panneau latéral, ni inspecteur, ni barre Production : le visualiseur prend toute la largeur avec sa barre de transport (volume de contrôle, retour au début, image précédente et suivante, lecture, boucle, le timecode, guides de cadrage, format d’image, résolution et plein écran), et affiche à côté du volume le plan sous la tête de lecture (« Plan 2/6 · Le port »). Vous entendez le même mixage que dans les autres espaces : le son des plans de V1 et les pistes audio, avec leurs muets, solos, faders et effets.

- **Timeline.** Celle des autres espaces, avec sa barre d’outils, ses rangées (**Titres**, **Prompts**, **Frames**, **V1 · Vidéo** et les pistes audio) et sa règle. Cliquez ou glissez sur la règle pour déplacer la tête de lecture ; sélectionnez et modifiez comme ailleurs. **Ajuster** montre tout le montage. Glissez la fine ligne au-dessus de la timeline pour lui donner plus ou moins de hauteur : Lecture partage cette hauteur avec Médias et Director IA.
- **Boucle.** Boucle activée, la lecture reprend au début à la fin du montage, ou au point d’entrée à la fin de la plage s’il y en a une. C’est la même chose dans tous les espaces.
- **Clavier.** Espace lance et arrête la lecture, les flèches avancent ou reculent d’une image (1 s avec Shift), Home revient au début et Fin va à la fin. Les autres raccourcis de la timeline agissent comme dans les autres espaces.
- Un plan encore sans média montre son nom et son instruction, sans le bouton **Générer des brouillons**. L’aperçu d’une prise ou d’un média source reste dans l’espace où vous l’avez ouvert : Lecture montre toujours le montage. Les boutons du panneau latéral et de l’inspecteur de la barre projet sont grisés ; les panneaux reviennent dans les autres espaces, où l’inspecteur montre ce que vous avez sélectionné dans Lecture.

### Director IA

Le panneau de gauche a quatre onglets. Un point sur **Direction** signale qu’il y a des points à vérifier, **Résultats** affiche le nombre de prises et **File** le nombre de prises en attente ou en cours.

- **Direction.** Montre ce qui guide la génération sur la plage courante : la direction globale, l’instruction locale, les références et frames, avec **Voir le récapitulatif de génération**. En dessous : **Points à vérifier**, la liste des contradictions de direction et des raccords de couleur à corriger (chaque raccord de couleur vient avec **Raccorder** et **Utiliser la dernière image du plan précédent**, chapitre 12), la section de la vérification de continuité de l’assistant (titrée **À vérifier**) avec son bouton **Demander à l’assistant de vérifier les raccords** (chapitre 10), une ligne qui rappelle que le moteur se règle dans la barre Production, avec **Modifier le moteur…** (chapitre 8), et la **Direction globale** elle-même, en cinq champs (univers et intention, personnages et identité, direction photographique, palette et éclairage, rythme et continuité), avec un compteur sur 4000 caractères. Chaque champ a un lien **Bibliothèque & assistant**. Le bouton en forme d’engrenage, **Modifier le moteur**, ouvre la fenêtre des options du moteur (chapitre 8).
- **Références.** Quatre familles : **Images et identité**, **Décors**, **Guides de mouvement** et **Son**. Une référence est globale (elle accompagne toutes les générations) ou ne s’applique qu’à une plage ; **Associer à la plage** règle le second cas. **Référence** en ajoute une, et **Recadrer un plan depuis la 3D…** ouvre Recadrer depuis la 3D sur le plan sélectionné, ou celui sous la tête de lecture (voir Recadrer depuis la 3D plus bas). Le centre montre la planche de références, en deux groupes, **Direction globale** et **Sur la timeline**, avec un champ de recherche. Glissez une vignette sur la piste Frames pour l’ancrer à un moment précis. Un nouveau projet n’a aucune référence : la planche le dit, et **Référence** ajoute la première. Une référence **Son** est une voix, une musique ou une ambiance : sélectionnez-la et choisissez son type et son son dans l’inspecteur (un son du projet, **Bibliothèque** ou **Depuis l’ordinateur**) ; sa carte montre la durée du son et un lecteur. Quand la famille **Son** est ouverte, la ligne au-dessus des familles dit ce que le moteur du projet fait de ce son (chapitre 13, Le son qui accompagne la génération).
- **Résultats.** Les cartes de prise de chaque plan (chapitre 9) et **Assembler les prises choisies**.
- **File.** Vos prises qui attendent le moteur ou sont en cours, dans l’ordre où elles passent, avec **Passer en tête de file** et **Annuler** (chapitre 8, Suivre les prises).

#### La bible

En bas de l’onglet **Direction**, la **Bible** réunit une fiche par personnage récurrent et une par lieu. Une fiche de personnage a une **Étiquette visuelle**, courte et concrète (« la femme rousse au ciré marine »), **Visage et costume**, un paragraphe fixe, et des **Accessoires** ; une fiche de lieu a une **Étiquette visuelle** et une **Description**. Une fiche peut être liée à des références **Images et identité** (un personnage) ou **Décors** (un lieu) du projet : c’est facultatif, et seul MiniMax H3 en Ref2VA s’en sert, en décrivant une référence liée envoyée avec un plan par les mots de la fiche. **Supprimer la fiche** la retire aussi des plans qui la distribuaient.

Vous distribuez des fiches dans un plan dans la section **Distribution** de l’éditeur de plan ou de l’inspecteur : cochez ses personnages et choisissez son lieu. Les fiches sont alors répétées mot pour mot dans le prompt de ce plan, au format de son moteur : en définitions de sujets en tête du prompt avec MiniMax H3, après l’action dans un seul paragraphe avec LTX, avant l’action avec Wan et les modèles cloud. Écrivez l’étiquette visuelle de chaque personnage distribué dans l’instruction du plan, de la même façon (« La femme rousse au ciré marine ouvre la porte. ») : l’éditeur de plan, l’inspecteur et l’estimation signalent son absence, et l’estimation signale aussi un prompt Wan qui dépasse les 512 jetons que lit Wan. Une fiche sans étiquette n’entre dans aucun prompt. Le texte seul ne tient pas un visage : une première image cohérente ou les références de Ref2VA restent le moyen le plus sûr.

Le champ **Personnages et identité** de la direction globale fonctionne comme avant : son texte est ajouté à chaque plan. Tant qu’il est rempli, la Bible propose **Convertir en fiche** : le texte devient une fiche de personnage distribuée dans tous les plans, avec ses premiers mots pour étiquette (vérifiez-la), et le champ est vidé. **Édition › Annuler** le rétablit.

### Storyboard

Le Storyboard a deux vues, choisies par **Grille** et **Bande** dans son en-tête (Fenêtre › Storyboard en bande) ; il s’ouvre sur la bande.

#### La bande

La bande montre les plans à l’échelle du temps : le rythme du montage se lit d’un coup d’œil. En haut, une vue d’ensemble fine de toute la séquence : chaque plan dans la couleur de son étape, un plan en échec en rouge, un plan en cours hachuré, un trait orange sur un raccord à vérifier, les plans en pointillé d’un découpage proposé et la fenêtre visible ; cliquez ou glissez dessus pour faire défiler la bande. Dessous, alignés sur le même temps :

- **Morceau** : la règle et les parties du morceau, c’est-à-dire les repères (M) posés dessus ;
- **V1 · Plans** : un bloc par plan, aussi large que sa durée, avec la vignette de sa prise répétée sur le bloc, ou ses images de début et de fin autour d’une zone hachurée tant qu’il n’a pas de prise. Le bloc porte son numéro, la progression d’une prise en cours (ou **En file**), **Échec** quand sa dernière prise a échoué, **Prompt modifié** ou **Aucune instruction**, sa durée, l’icône réglages d’un moteur propre, l’icône d’onde de son son et sa distribution. Un repère sur la jonction de deux plans montre le raccord : vert quand il est mesuré, orange quand il demande un regard, avec les problèmes dans son infobulle ; cliquez dessus pour comparer les deux plans au moniteur ;
- **Prises** : jusqu’à quatre prises empilées sous chaque plan, la finale en haut, puis les candidates, les brouillons et les rejetées (hachurées), puis les prises en cours, en file ou en échec ; celles du plan choisi affichent leur lettre et leur étiquette. Cliquez sur une prise pour la voir au moniteur ;
- **Musique** : la forme d’onde des clips des pistes Musique ;
- **Sons de référence** : sous chaque plan, ce qu’il envoie à son moteur comme son de référence (pistes de référence et références sonores), en vert quand le moteur le suit, en gris quand il est mixé sur la prise.

Glissez un plan pour le déplacer ; glissez son bord droit pour changer sa durée : les plans suivants suivent, le morceau reste en place, le magnétisme cale la coupe sur les bords des plans et des sons, les repères et la tête de lecture, et l’infobulle dit où tombe la coupe. Ctrl et la molette zooment autour du pointeur ; **−**, **+**, le curseur et **Ajuster** font de même dans l’en-tête, qui porte aussi le magnétisme et **Plan**. Un double clic sur un plan ouvre l’éditeur de plan.

Sous la bande, le **moniteur** lit le montage comme le visualiseur, avec la fin du plan précédent à sa gauche et le début du plan suivant à sa droite, chacun avec le repère de son raccord. Avec une prise choisie dans la pile, ou avec les flèches haut et bas, le moniteur montre cette prise hors montage, avec **Rejetée**, **Candidate** et **Finale**, et Entrée l’utilise. Avec un raccord choisi, le moniteur compare côte à côte la dernière image du plan précédent et la première image du plan, avec les problèmes et leurs actions (**Raccorder la couleur**, **Utiliser la dernière image du plan précédent**). À côté du moniteur, l’**édition rapide** du plan choisi : son nom, son instruction (une modification marque les prises **Prompt modifié**, comme dans l’éditeur de plan), sa durée, son moteur, son nombre de brouillons, ses images clés, sa distribution et son son, **Générer N brouillons** et **Éditeur de plan**. Le panneau de gauche et la timeline sont masqués dans cette vue, puisque la bande porte leurs pistes ; l’inspecteur se ferme à l’ouverture de la bande et revient par le bouton Inspecteur.

#### Synopsis et découpage

**Synopsis et découpage**, dans l’en-tête de la bande (D, Production › Synopsis et découpage, ou le bouton du panneau de gauche), ouvre une fenêtre sous la bande, qui reste utilisable. Elle a trois onglets :

- **Découpage** : le synopsis, les noms de la bible qu’il contient, et trois méthodes. **Par phrases** est le découpage d’avant (une phrase, un plan de 3 à 7 s). **Sur le morceau** remplit les parties du morceau à la longueur moyenne choisie (2 à 8 s) et y répartit les phrases dans l’ordre ; il faut un morceau sur une piste Musique. **Assistant** le demande à l’assistant PotionUI, dont la proposition revient dans la même liste. Chaque plan proposé peut être gardé ou non, renommé, recevoir une autre instruction, être raccourci ou allongé, coupé en deux, fusionné avec le suivant, déplacé et retiré ; il reçoit les personnages et le lieu de la bible que nomme sa phrase. Les plans proposés apparaissent en pointillé sur la bande et dans la vue d’ensemble, à leur durée et à leur place, avant que rien ne change. **Insérer** les place à la fin ou après le plan choisi ; **Ajouter N plans** (Ctrl+Entrée) les ajoute, et Annuler les retire.
- **À produire** : les brouillons restants et les plans à passer en final, avec **Générer leurs brouillons**, les prises dans la file et les plans à faire, chacun avec **Voir**.
- **À vérifier** : les raccords à vérifier (avec leurs actions), les prises en échec (**Réessayer**), les plans dont l’instruction a changé après leurs prises (**Générer de nouveaux brouillons**) et les plans sans instruction (**Écrire l’instruction**), chacun avec **Voir**. Le bouton de l’en-tête en donne le nombre.

#### La grille

À gauche : le **Synopsis** (une phrase devient un plan) et **Proposer un découpage**. Le **Découpage proposé** liste les plans : cochez ceux à garder, renommez-les et cliquez sur **Ajouter N plans à la fin**. Le découpage de ce bouton est simple : il se contente de couper le synopsis en phrases (son infobulle dit « Coupe par phrases ; demandez le vrai découpage à l’assistant »). L’assistant fait un vrai découpage et remplit la même liste (chapitre 10). Puis **À produire**, avec **Brouillons restants** et **Passage en final** (le nombre de plans et la durée qu’il reste à faire pour chacun), et **Continuité**, qui liste les raccords de couleur à vérifier, chacun avec **Raccorder la couleur** et **Utiliser la dernière image du plan précédent** (chapitre 12).

Au centre : une carte par plan, dans l’ordre, avec son numéro, sa durée, son nom, son étape (**Source**, **À générer**, **Brouillon** ou **Final**), son nombre de prises, **Modifier** et son instruction locale. **Modifier** ouvre l’éditeur de plan (plus bas). Sur un plan sans prise, cliquer sur l’instruction ouvre aussi l’éditeur de plan ; dès que le plan a une prise, son instruction est seulement affichée, pour qu’un clic ne change pas ce dont les prises sont parties. Quand le plan a été modifié après sa prise, la vignette porte **Prompt modifié** (la prise posée sur le plan, ou toutes les prises quand aucune n’y est posée, est plus ancienne que la modification). Une icône de curseurs après le nombre de prises dit que le plan fixe son propre moteur ; survolez-la pour le détail (« Moteur propre : LTX-2.5 · Final · graine 42 »). Le bloc du plan sur la timeline porte la même icône. Une icône de forme d’onde dit que le plan envoie du son avec sa génération (une référence sonore ou une piste de référence, chapitre 13) ; survolez-la pour lire ce qu’en fait son moteur : en vert, « Conditionne la génération : MiniMax H3 suit ce son. » ; en gris, « Sera mixé sur la prise, pas utilisé comme guide. » ; en ambre, « Ignoré par ce moteur : le son reste seulement dans le montage. » Glissez une carte pour la déplacer. Les boutons d’une carte apparaissent au survol ou quand la carte est sélectionnée : le bouton principal suit l’étape, **Générer**, **Passer en final**, **Voir les prises** ou **Régénérer** ; à côté de **Générer**, le nombre de brouillons du plan (×1 à ×8, chapitre 8) ; et trois icônes montrent le plan dans le visualiseur, insèrent un plan après lui et le suppriment. Tant qu’une prise du plan est en cours, la carte montre son étape et sa progression, comme le bloc du plan sur la timeline, et le bouton est désactivé. L’en-tête compte les plans par étape, en ajoute un avec **Plan** et règle la taille des vignettes ; une tuile **Nouveau plan** à la fin fait la même chose. Dans cet espace, les flèches gauche et droite déplacent la sélection vers le plan précédent ou suivant.

#### L’éditeur de plan

**Modifier** sur une carte du Storyboard, ou **Modifier le plan…** dans l’inspecteur, ouvre la fenêtre « Plan · <nom> ». Elle réunit ce dont une prise du plan est faite :

- **Texte de l’instruction locale**, avec **Bibliothèque & assistant**. Les alertes sur la direction s’affichent sous le texte.
- **Distribution** : les personnages et le lieu du plan, tirés de la bible (chapitre 4, La bible), avec une alerte quand l’instruction ne nomme pas un personnage distribué. Dessous, **Partie du prompt tirée des références** : la partie du prompt faite à partir des références et des fiches du plan, telle qu’elle partirait pour le moteur du plan (avec MiniMax H3 en Ref2VA, les définitions des sujets, les lignes de rétention et les citations dans le plan ; avec MiniMax H3 sinon, les définitions des sujets ; avec LTX, Wan et les modèles cloud, les fiches de la bible). **Remplacer pour ce plan** permet de la modifier : votre texte part tel quel à la place du texte composé, et **Revenir au texte composé** annule le remplacement. Quand une référence ou une fiche change ensuite, la fenêtre signale que le texte composé a changé et le montre ; **Garder mon texte** conserve le vôtre. Puis **Prompt envoyé au moteur** : le prompt complet que le plan enverrait avec vos modifications, composé pour le moteur du plan (son instruction, sa distribution et la direction globale), avec les alertes sur sa longueur.
- **Durée**, au plus la longueur du média du plan quand il en a un (« Au plus 5,0 s avec le média du plan. »).
- **Images clés** : la **Première image** et la **Dernière image**. Cliquez sur l’une pour choisir une image du projet, ou sur **Bibliothèque** ou **Depuis l’ordinateur** pour en importer une (chapitre 6) ; **Retirer** l’enlève. **Recadrer depuis la 3D…** filme une image sous un autre angle et en ramène les captures ici (voir Recadrer depuis la 3D plus bas).
- **Références**. **Héritées du projet** liste les références globales, chacune avec une case **Exclure** : une référence exclue n’est pas envoyée avec ce plan, et les autres plans la gardent. **Propres au plan** liste les références du plan, avec leur nom et leur type ; **Ajouter au plan** en ajoute une à partir d’une image (du projet, de la bibliothèque ou de votre ordinateur), et la corbeille en retire une. La ligne du haut compte les références que le plan envoie (« 2 références pour ce plan »). Un moteur envoie au plus 9 images, 3 vidéos et 3 fichiers audio par plan (chapitre 8) : celles qu’on exclut laissent la place aux suivantes. **Ajouter un son** ajoute une référence sonore propre au plan (un son du projet, **Bibliothèque** ou **Depuis l’ordinateur**), avec son type, **Voix**, **Musique** ou **Ambiance** ; les sons montrent leur durée et un lecteur. **Pistes de référence** liste les pistes audio cochées **Référence pour la génération** (chapitre 13), chacune avec ce qu’elle contient sous le plan (« 1 clip entre 0,0 s et 5,0 s », ou « Rien entre … : rien n’est envoyé ») et une case **Exclure** qui écarte la piste pour ce plan seulement. La dernière ligne dit ce que le moteur du plan fait de son son : « Conditionne la génération : MiniMax H3 suit ce son. », « Sera mixé sur la prise, pas utilisé comme guide. » ou « Ignoré par ce moteur : le son reste seulement dans le montage. »
- **Image de début depuis les références** (repliée tant que le plan n’a pas de candidate) : un modèle d’image retouche les images Identité et Décors du plan pour en faire son image de début, ou de fin, que le moteur vidéo anime ensuite. Choisissez le **Modèle d’image** (les presets de votre instance qui retouchent à partir de plusieurs images : Qwen-Image-2.1, FLUX 3 Klein, Qwen-Image Edit 2511, ou Nano Banana dans Gemini Images ; le choix est gardé pour le projet), **Image de début** ou **Image de fin**, et 2 à 4 **Candidates**. **Images envoyées, dans cet ordre** montre ce qui part, numéroté : le décor d’abord (une capture de Recadrer depuis la 3D en image de début, l’image d’où vient sa scène, les références Décors), puis les personnages, les objets et les styles ; la première image est celle qui est retouchée et donne son cadre à l’image, et celles qui dépassent la limite du modèle sont atténuées. La ligne dessous donne le temps (dès qu’une candidate de ce modèle a été mesurée), la mémoire et le quota GPU, ou le coût pour un administrateur. **Créer 2 candidates pour l’image de début** les lance ; chacune est une candidate A, B… du plan, qui attend dans la file comme une prise. Sur une candidate finie, **En début** ou **En fin** la place dans les **Images clés** de la fenêtre (enregistrez le plan pour la garder), l’icône pouce baissé la rejette, et la corbeille la supprime (son image reste dans votre historique). Une candidate en échec a **Relancer**. Quand le modèle choisi pour le projet n’est plus installé ou ne vous est plus assigné, la section le dit et en demande un autre.
- **Brouillons** : combien de brouillons les boutons Générer du plan font d’un coup (chapitre 8).
- **Moteur** : ce avec quoi le plan est généré. Chaque champ part de la valeur du projet : **Comme le projet (Wan 2.1 / 2.2)** pour le moteur, **Comme le projet (FL2VA)** pour le profil, **Comme la barre Production** pour la qualité, **Aléatoire** pour la graine. Choisissez une autre valeur pour la donner à ce plan seulement : **Preset ou modèle** (les moteurs du menu de la barre Production), **Profil** (ceux que le moteur choisi ne sait pas générer sont grisés), **Qualité** (**Brouillon** ou **Final**, quoi que dise la barre) et **Graine** (le bouton à flèches en tire une). Avec une graine, la première prise de chaque génération la prend et les suivantes les graines d’après : générer à nouveau donne les mêmes prises. **Revenir au projet** les efface toutes. Un réessai ou un **Passer en final** garde le moteur et la graine de sa prise.

**Enregistrer** applique le tout d’un coup, et **Édition › Annuler** ramène le tout. Quand le plan a des prises, la fenêtre le dit (« Ce plan a 4 prises. Enregistrer une modification les garde et les marque « Prompt modifié ». ») et, dès que vous changez l’instruction, la durée, une image ou une référence, le pied de la fenêtre prévient « Les prises du plan seront marquées « Prompt modifié » ». Enregistrer ne supprime aucune prise : elles restent, avec **Prompt modifié** sur leur carte et sur la carte du Storyboard, jusqu’à ce que vous génériez de nouveaux brouillons. Changer seulement le nombre de brouillons ou le moteur ne marque rien. Modifier l’instruction d’un plan ailleurs (l’inspecteur de l’instruction locale, l’éditeur de prompt de la timeline, la bibliothèque, ou l’assistant quand vous approuvez sa réécriture) marque les prises de la même façon.

Une capture de la fenêtre, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/shot-editor.png`, et une de sa section **Moteur** avec des réglages propres au plan dans `docs/screenshots/shot-engine.png`.

#### Recadrer depuis la 3D

**Recadrer depuis la 3D** filme une image sous un autre angle, pour la première ou la dernière image d’un plan. L’outil transforme l’image en scène 3D, un Gaussian Splat (un nuage de petites taches colorées dans lequel une caméra peut se déplacer), vous laisse y placer une caméra et capture ce qu’elle voit. Il s’ouvre sur un plan depuis trois endroits :

- **Recadrer depuis la 3D…** dans la section **Images clés** de l’éditeur de plan ;
- **Recadrer un plan depuis la 3D…** dans l’onglet **Références** de Director IA, pour le plan sélectionné ou celui sous la tête de lecture ;
- **Plan › Recadrer depuis la 3D…**, que trouve aussi la recherche de commande, pour le même plan.

Sans plan sélectionné ni sous la tête de lecture, la page indique « Sélectionnez un plan vidéo. »

**La source.** La fenêtre « Recadrer depuis la 3D » nomme le plan et ses temps. Sous **Source**, choisissez ce qu’il faut recadrer :

- **Première image du plan** : la première image du plan, telle que l’éditeur de plan la montre quand vous avez ouvert la fenêtre depuis lui ;
- **Une autre image** : une image du projet, ou **Choisir dans la bibliothèque…** pour une image de votre bibliothèque PotionUI, qui rejoint les médias du projet ;
- **Une scène existante** : une scène déjà construite dans ce projet.

Une image n’est transformée en scène qu’une fois. Quand elle en a déjà une, la fenêtre indique « Scène déjà construite : « … » » et la montre, ou dit que la scène est en construction et la montre dès qu’elle est prête. Sinon, cliquez sur **Construire la scène 3D** : la scène est construite dans la file de génération, comme une prise, en quelques secondes à une minute, et compte dans vos minutes GPU. La vue affiche sa progression avec **Annuler**, et un message signale quand la scène est prête ou n’a pas pu être construite. Une scène en échec donne la raison avec **Réessayer**.

**Le cadrage.** La vue dessine la scène dans le cadre de votre projet. Glissez pour orbiter autour de la cible, glissez avec le bouton droit (ou avec Maj) pour déplacer la caméra, utilisez la molette pour avancer ou reculer, et la molette avec Alt pour changer la focale. Au clavier, quand la vue a le focus (Tab, ou un clic dedans), les flèches font orbiter la caméra, Maj et les flèches la déplacent, + et − l’avancent et la reculent, et 0 revient à la vue d’origine. Sous **Cadrage**, **Focale** et **Roulis** règlent l’objectif et l’inclinaison de la caméra, et **Vue d’origine** revient à la caméra de l’image. En haut à gauche de la vue s’affichent la focale, les angles de champ vertical et horizontal et le roulis ; la vue de dessus, en bas à droite, montre la caméra d’origine (cercle), la cible (carré) et la caméra courante.

Une image ne montre qu’un côté des choses : la caméra reste donc dans la zone fiable de la scène, au plus 15° autour de la vue d’origine, 25 % de sa distance en avant ou en arrière, et aucune focale plus large que celle de l’image. La caméra s’arrête au bord de cette zone. La jauge en bas à gauche indique l’écart à la vue d’origine et la part de la zone utilisée ; elle passe à l’orange avec « Trous probables » au-delà des deux tiers (10°, ou environ 17 %), là où des zones vides commencent à apparaître derrière les objets.

**Les captures.** **Capturer la première image** et **Capturer la dernière image** prennent chacune ce que voit la caméra, à la résolution de votre projet, et la montrent avec la part d’image vide (« Environ 4 % de l’image est vide : des trous dans la scène. », en orange au-delà de 3 %). Deux captures sous deux angles font passer la caméra de l’un à l’autre pendant la prise (FL2VA) ; une première image seule fait partir la prise du nouvel angle, et une dernière image ne sert qu’avec une première image. La croix à côté d’une capture la retire.

**Placer dans le plan** garde les captures comme images du projet, enregistrées dans votre bibliothèque PotionUI, puis :

- ouverte depuis l’éditeur de plan, la fenêtre les met dans les **Images clés** de l’éditeur et y revient (« Les captures vont dans l’éditeur de plan et sont enregistrées avec lui. »). Cliquez sur **Enregistrer** dans l’éditeur de plan pour les garder ; **Annuler** y garde les images que le plan avait, et les images capturées restent dans les médias du projet ;
- ouverte depuis Director IA ou le menu Plan, elle les place aussitôt en première et dernière images du plan (« Captures placées en première et dernière images de « Plan 2 » », avec **Annuler**). Si le plan a déjà une telle image, une fenêtre demande d’abord (« Remplacer la première image ? », ou « Remplacer la première et la dernière image ? » pour les deux).

**Annuler** revient à l’éditeur de plan, ou ferme la fenêtre. Une image capturée ainsi porte un cube sur la piste **Frames** de la timeline, et l’inspecteur de la frame nomme sa scène. Quand vous créez une image de début depuis les références pour ce plan (voir L’éditeur de plan plus haut), l’image d’où vient la scène l’accompagne comme décor.

Si la carte graphique cesse d’afficher la vue 3D, la vue le signale : cliquez sur **Réessayer**. Si elle propose **Recharger la page**, le plugin a été mis à jour pendant que la page était ouverte.

**Les projets faits avec une version antérieure** gardent leurs scènes. Une scène tirée d’une image d’une vidéo, ou un splat importé à l’époque, figure sous **Une scène existante** ; un splat importé sans vue d’origine se déplace librement, sans jauge, et une scène Blender n’est plus affichée. Les plans 3D et les Control video d’un tel projet n’apparaissent plus sur la timeline. La vidéo de référence de chaque plan 3D devient une référence **Guides de mouvement** du plan qu’elle guidait, de type Control video : avec le profil Ref2VA, MiniMax H3 reprend son mouvement dans le plan (chapitre 8).

Une capture de la fenêtre avec les deux images capturées, dans le thème sombre de l’interface en français, se trouve dans `docs/screenshots/reframe-from-3d.png`. Sa scène est une scène d’essai faite par un script, pas une scène construite par Image to Splat.

### Mixage

L’**Atelier Sound design**, les **Sons du projet** (glissez-en un vers une piste, ou utilisez son bouton plus pour l’ajouter à la tête de lecture), les **Rôles** (**Dialogue**, **Musique**, **Ambiance**, **SFX**) avec leur nombre de pistes, et la console de mixage, qui prend la place de la timeline. Elle commence par la tranche **V1 · Plans**, le son des vidéos de V1, avec son vumètre, **M** et **S** ; viennent ensuite les pistes audio avec leurs faders, **M** et **S**, panoramique, égaliseur, compresseur, filtre, envois de réverbération et de délai, vumètres et un mode d’automation. Le centre est le visualiseur. Les quatre pistes d’un nouveau projet sont vides, et **Sons du projet** indique « Aucun son dans ce projet. » tant que vous n’en importez pas (chapitre 6). La console joue les fichiers audio que vous importez (chapitre 13) ; les sons que l’atelier prépare sont synthétisés par votre navigateur. L’atelier et les courbes d’automation sont simulés : voyez le chapitre 17.

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

**Fichier › Historique des versions…** ouvre la fenêtre **Historique des versions** (« Chaque enregistrement crée une version »). Elle liste les versions du projet ouvert, la plus récente en premier. Chaque ligne montre le numéro (« Version 7 »), la date et l’heure, secondes comprises, et le nombre de plans. Une capture de cette fenêtre, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/version-history.png`. Une version issue d’une restauration ajoute « Restaurée depuis la version N ». Une version écrite par l’assistant ajoute « Assistant » (chapitre 10). La version sur laquelle vous travaillez porte le badge **Actuel** et ne peut pas être sélectionnée.

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

Les médias viennent de deux endroits : votre bibliothèque et votre galerie PotionUI, ou l’ordinateur sur lequel tourne votre navigateur. Chaque endroit a son bouton : **Bibliothèque** (un dossier) et **Depuis l’ordinateur** (une flèche vers le haut), côte à côte dans l’en-tête du panneau Médias, dans un panneau Médias vide, dans les **Sons du projet** de l’espace **Mixage** et dans la console ; le menu **Importer** de la barre projet propose les deux.

- **Images et vidéos de la bibliothèque.** **Fichier › Importer depuis la bibliothèque…** (Ctrl+I) et les boutons **Bibliothèque** ouvrent la fenêtre **Importer des images et des vidéos**. C’est le sélecteur PotionUI de votre bibliothèque : les fichiers que vous avez téléversés dans PotionUI et les générations que vous y avez copiées.
- **Depuis la galerie.** **Fichier › Depuis la galerie PotionUI** ouvre **Importer depuis la galerie**, avec vos générations passées. Chaque fichier d’une génération se choisit séparément. Seules les images et les vidéos peuvent être choisies.
- **Audio de la bibliothèque.** **Audio › Importer un son de la bibliothèque…** et les boutons **Bibliothèque** des **Sons du projet** et de la console ouvrent **Importer des fichiers audio**, le sélecteur de votre bibliothèque limité à l’audio.
- **Depuis l’ordinateur.** **Fichier › Importer depuis l’ordinateur…** (Ctrl+Alt+I) et les boutons **Depuis l’ordinateur** ouvrent la fenêtre de fichiers de votre système, où vous pouvez choisir plusieurs images, vidéos et fichiers audio à la fois. **Audio › Importer un son depuis l’ordinateur…** et les boutons **Depuis l’ordinateur** des **Sons du projet** et de la console ne proposent que des fichiers audio ; un autre type de fichier y est refusé (« … ne peut pas être importé ici : seuls les fichiers audio sont acceptés. »).
- **Par dépôt de fichiers.** Faites glisser des fichiers de votre ordinateur sur le panneau Médias : un cadre s’affiche pendant le survol, rouge avec « Seuls les images, les vidéos et les fichiers audio peuvent être importés » quand ce que vous faites glisser n’est pas accepté. Ou déposez-les sur la timeline : ils sont placés à l’instant où vous les déposez, que montrent un trait et « Déposer à » suivi de l’instant. Les images et les vidéos vont sur la piste vidéo **V1**, en nouveaux plans à la suite, ou sur **Frames** ; les fichiers audio vont sur une piste audio. Une piste qui ne prend pas ce que vous faites glisser est encadrée de rouge (« Non accepté sur cette piste »), et y déposer vous indique où va chaque type.

Les fichiers que vous pouvez apporter de l’ordinateur sont ceux que PotionUI accepte : images `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` et `.bmp`, vidéos `.mp4`, `.webm`, `.mov`, `.mkv` et `.avi`, audio `.wav`, `.mp3`, `.ogg`, `.flac`, `.m4a` et `.aac`. Un fichier d’un autre type est refusé avant tout envoi, par exemple « « notes.pdf » ne peut pas être importé : seuls les images, les vidéos et les fichiers audio sont acceptés. »

Les fichiers de l’ordinateur sont envoyés dans votre bibliothèque PotionUI un par un. Le panneau **Imports**, en bas à droite, les liste avec une barre et un pourcentage chacun, « En attente » pour ceux qui n’ont pas commencé et un bouton pour annuler chacun ; un fichier indique « Importé » une fois dans le projet, et le panneau se ferme de lui-même. Chaque fichier devient un élément de votre bibliothèque : vous le retrouvez dans les sélecteurs **Bibliothèque** de tous vos projets et dans la bibliothèque PotionUI. Un fichier dont le contenu est déjà dans votre bibliothèque n’est pas stocké deux fois, et un fichier déjà présent dans le projet est compté à part, comme avec les sélecteurs. Le plus gros fichier et la place dont vous disposez sont ceux de votre plan de stockage PotionUI : quand un fichier ne peut pas être stocké, la page le dit avec la raison, par exemple « « Rushes.mov » n’a pas pu être importé : le fichier est trop volumineux pour le serveur. » Captures, dans les thèmes sombre et clair de l’interface anglaise : des fichiers glissés sur le panneau Médias dans `docs/screenshots/media-import-local.png`, le panneau **Imports** pendant leur envoi dans `docs/screenshots/upload-progress.png`, et un fichier glissé sur la timeline dans `docs/screenshots/timeline-drop.png`.

Dans chaque sélecteur, cochez plusieurs fichiers et confirmez-les ensemble. Les fichiers apparaissent alors dans le panneau Médias et la page affiche, par exemple, « 2 fichiers importés ». Un média déjà présent dans le projet (même origine) n’est pas importé de nouveau : la page le compte à part, par exemple « 2 fichiers importés · 1 fichier déjà présent dans le projet », ou « 1 fichier déjà présent dans le projet » quand rien n’est nouveau. Quand certains ne peuvent pas être importés, elle ajoute, par exemple, « 1 fichier n’a pas pu être importé » : le fichier n’est plus disponible, ou son type n’est pas accepté par la fenêtre. Si votre serveur n’a pas de sélecteur, la page indique « Le sélecteur de médias n’est pas disponible sur ce serveur. »

Un import depuis la bibliothèque ou la galerie ne copie rien : le projet garde une référence à l’élément de la bibliothèque ou au fichier de la galerie, et l’adresse que la page utilise pour l’afficher. Un fichier de l’ordinateur est copié une fois, dans votre bibliothèque, et le projet garde une référence à cet élément. Si vous supprimez le fichier de PotionUI, le projet ne peut plus l’afficher ni le lire.

### Dans le panneau Médias

Après l’import, votre navigateur lit la durée et la taille de chaque fichier. La durée s’affiche en bas à droite de la vignette. Pour l’élément sélectionné, le panneau montre **Durée**, **Format**, **Collection** et **Origine** : **Galerie** ou **Bibliothèque** (un fichier de l’ordinateur est dans votre bibliothèque, il indique donc **Bibliothèque**) ; la vignette porte le même mot. La cadence d’une vidéo importée vient de la bibliothèque quand elle la connaît, et s’affiche après la taille (par exemple « 1280×720 · 25 i/s ») ; sinon, et pour un fichier de la galerie, **Format** n’indique que la taille. Les pastilles de collections rangent les images sous **Images**, les vidéos sous **Vidéos** et les fichiers audio sous **Audio**. **Générés** contient les vidéos des prises terminées du projet (chapitre 9). Une capture du panneau après un import se trouve dans `docs/screenshots/media-import.png`.

### Vignettes

Une image est sa propre vignette. Pour une vidéo, la page utilise la vignette que PotionUI a faite quand il y en a une, sinon une image que votre navigateur capture dans le fichier. Les vignettes ne sont pas enregistrées dans le projet : elles sont refaites à l’ouverture du projet. Elles s’affichent partout où un média ou un plan montre son image : le panneau Médias, l’inspecteur, la timeline et le visualiseur.

### Lecture

- **Vidéo et images.** Mettez le média au montage (**Au montage**, ou glissez-le vers la timeline). Le visualiseur lit alors la vraie vidéo en suivant la tête de lecture, ou affiche l’image, avec les fondus et les réglages de couleur du plan. Pour regarder un média seul, double-cliquez dessus ou cliquez sur **Prévisualiser** : le visualiseur le montre, une vidéo avec les commandes de votre navigateur et un fichier audio avec un lecteur audio, et **Revenir à la séquence** vous y ramène.
- **Son d’une vidéo.** Le visualiseur joue le son de la vidéo de chaque plan avec son image, à sa place dans la séquence, avec les fondus du plan. Il passe par la console : la tranche **V1 · Plans** montre son niveau, et le fader master et le volume du moniteur du visualiseur agissent dessus. Coupez-le pour un plan (le haut-parleur du plan sur la timeline, ou **Son du plan** dans l’inspecteur), pour tous les plans (**M** dans l’en-tête de V1), ou écoutez-le seul (**S**) (chapitre 13). Une prise générée sans piste son reste muette, comme à l’export. Votre navigateur lit le son dans le fichier une seconde fois, à côté de l’image, à partir d’une seconde et demie avant le début du plan.
- **Audio.** Un fichier audio placé sur une piste passe par sa tranche de la console. Les faders, muet et solo, panoramique, égaliseur, compresseur, filtre et envois agissent sur le vrai son, les vumètres le montrent, et le clip dessine la forme d’onde du fichier dans la timeline (chapitre 13).

Ce qui est simulé ici : les sons de l’atelier Sound design, que votre navigateur synthétise (chapitre 17). Les prises de la génération réelle sont des vidéos ordinaires et se lisent comme n’importe quelle vidéo (chapitre 9). Quand le fichier du média d’un plan n’est plus accessible (vous l’avez supprimé de votre bibliothèque ou de votre galerie), le visualiseur affiche **Média hors ligne** (« Le fichier source de “…” n’est plus disponible : importez-le à nouveau ou choisissez une prise. ») et la vignette du plan sur la timeline aussi.

## 7. Inspecteur

L’inspecteur suit la sélection et son titre dit ce qui est sélectionné : **Plan vidéo**, **Clip audio**, **Titre**, **Instruction locale**, **Frame de référence**, **Marqueur**, **Référence** ou **Tranche de console**. Pour un plan, il commence par une vignette, le nom (cliquez dessus pour renommer le plan), l’étape et les temps, et il a trois onglets :

- **Plan.** **Modifier le plan…**, qui ouvre l’éditeur de plan (chapitre 4), avec à côté le nombre de brouillons du plan ; un raccourci vers l’action suivante (**Générer des brouillons**, ou **Passer la prise A en final**) avec le moteur qu’il utilisera (« Sur » suivi du moteur), **Durée et source** (la durée, l’endroit où le plan commence dans sa source et la longueur de la source), **Images clés** (la **Première image** et la **Dernière image** du plan, et le bouton **Utiliser la dernière image du plan précédent** ; chapitre 12), **Fondus** (**Entrée** et **Sortie**), pour une vidéo **Son du plan** (**Couper le son du plan**, avec une ligne qui dit si le plan est entendu, et sinon pourquoi), la **Distribution** du plan tirée de la bible (chapitre 4, La bible), la **Marque** (**Aucune**, **Favori** ou **Rejeté**) et trois icônes pour couper le plan au milieu, le dupliquer et le supprimer.
- **Prises.** Les cartes de prise du plan, regroupées par étiquette (**Finale**, **Candidates**, **Brouillons**, **Rejetées**), l’interrupteur **Masquer les prises rejetées** quand il y en a, et un bouton qui fait des brouillons de plus, avec à côté le nombre de brouillons du plan (par exemple « 3 brouillons de plus » ; chapitres 8 et 9).
- **Couleur.** Le scope de luminance, le raccord avec le plan précédent, les préréglages et les réglages fins (chapitre 12).

Les autres éléments ont leur propre panneau :

- **Clip audio :** sa piste, son début, sa durée, son gain, son interrupteur **Référence pour la génération**, ses fondus, la section **Tranches** (chapitre 13), et un bouton qui ouvre sa tranche dans la console.
- **Titre :** le texte, le sous-titre, le début et la durée.
- **Instruction locale :** le texte, le lien **Bibliothèque & assistant**, le bouton **Éditeur**, les avertissements sur la direction, le début, la durée, l’influence, et la direction globale appliquée.
- **Frame de référence :** l’image (choisie parmi les images du projet, qu’un nouveau projet n’a pas), la position, le rôle (début, fin, transition, identité, style), l’intensité de son influence et, pour une capture de Recadrer depuis la 3D, la scène où elle a été capturée.
- **Marqueur :** le libellé et la position.
- **Référence :** le nom, le rôle, la portée (**Direction globale** ou **Moment précis**) et le plan concerné.
- **Tranche de console :** le nom, le rôle, son interrupteur **Référence pour la génération**, **Découper sur les plans** pour tous ses clips (chapitre 13), les effets (**Égaliseur**, **Compresseur**, **Filtre**), les envois et **Supprimer la piste A2** (avec le nombre de clips audio qui partent avec elle ; chapitre 13).

Sans sélection, il montre le projet (format, profil H3, contenu), un rappel des principaux raccourcis et un bouton **Propriétés du projet…**.

## 8. Barre Production et génération

La barre Production se lit comme une phrase : une cible (**Plan**, **Plage** ou **Séquence**), la plage avec le nombre de plans et de prompts qu’elle contient, une qualité (**Brouillon** ou **Final**), le nombre de brouillons des plans visés, puis le moteur du projet : le **Moteur de génération**, son **Profil**, la **Marge** des pistes de référence quand un son peut guider la génération, le nombre de plans qui fixent leur propre moteur et **Modifier le moteur** (les curseurs) ; puis le bouton de la file (la liste), l’estimation et **Générer la sélection**. Quand la fenêtre est trop étroite pour tout montrer, ce qui ne tient pas passe dans **Autres réglages du moteur** (les points), au bout des réglages du moteur. Un nombre accompagné d’une icône d’alerte après les compteurs est le nombre de contradictions de direction dans la plage ; cliquez dessus pour les voir. La génération est réelle : une prise est une vidéo produite en arrière-plan par le moteur que vous choisissez.

### Choisir le moteur

- Le menu **Moteur de génération** liste ce que votre admin a activé et vous a attribué, en groupes qui portent le nom des backends. Un groupe au nom du backend de votre admin contient les presets vidéo qui tournent sur son matériel, par exemple **Wan 2.1 / 2.2**, **MiniMax H3** ou, sur une carte de 12 Go, **MiniMax H3 (12 GB)**. Chaque fournisseur cloud a son groupe, avec ses modèles vidéo par leur nom. Votre choix est enregistré avec le projet. Que le preset tourne sur ce poste ou sur un serveur d’atelier, c’est PotionUI qui le décide, et la carte de la prise vous le dit ensuite. Survolez le menu pour voir le groupe et, pour un preset qui tourne sur le matériel de l’admin, la mémoire libre de son GPU (« 16,0 / 24,0 Go libres »). Dans une fenêtre étroite, le menu passe dans **Autres réglages du moteur** (les points). Une capture du menu et de la barre qui l’entoure, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/engine-popup.png`.
- Sans moteur, le menu indique « Aucun moteur » et la barre dit « Aucun moteur de génération : un administrateur doit activer un preset vidéo ou un modèle cloud. » Un admin voit aussi le lien « Ouvrir les réglages du plugin ». Quand le moteur d’un projet n’est plus disponible, le menu indique « Moteur plus disponible » et la barre dit « Le moteur de ce projet n’est plus disponible : choisissez-en un autre. » Un projet d’une version antérieure qui nommait un moteur fictif est ramené au vrai moteur correspondant à son ouverture.
- **Qualité.** **Brouillon** fait des prises rapides à la résolution choisie par votre admin, ou à la plus proche que le moteur propose ; survolez-le pour la voir (« Brouillon rapide en 832×480 : valider mouvement et cadrage »). **Final** fait des prises à la plus grande résolution du moteur (« Qualité finale en 1280×720 : à réserver aux prises retenues »). Pour améliorer un brouillon qui vous plaît, **Passer en final** (chapitre 9) est en général le meilleur moyen : il garde l’image que vous avez choisie. La qualité choisie est enregistrée avec le projet, et la barre la reprend à son ouverture ; un plan peut fixer sa propre qualité dans son éditeur de plan (chapitre 4).
- **Profil.** FL2VA, Ref2VA ou Hybrid AV : la barre ne montre que les profils que le moteur sait générer, et rien quand il n’en sait générer qu’un. Survolez-le pour voir ce que fait le profil.
- **Marge** (0 à 10 secondes, 0 par défaut) élargit, avant et après chaque plan, la portion d’une piste de référence qui guide MiniMax H3 (chapitre 13). Elle n’apparaît que si un son peut guider la génération : MiniMax H3 avec Ref2VA, pour le projet ou pour un plan.
- Un plan peut fixer son propre moteur, son profil, sa qualité et sa graine dans son éditeur de plan (chapitre 4) ; la barre compte alors ces plans (« 1 moteur propre »), et ces réglages passent avant ceux du projet.
- **Modifier le moteur** ouvre une fenêtre avec toutes les options du moteur, telles que son preset les définit sur la page Générer : la vitesse, les pas, le sampler, le guidage, les modèles, les LoRA, les améliorations, etc., rangées selon les onglets et les sections du preset. Une valeur que vous fixez montre sa valeur par défaut en dessous et un bouton pour y revenir ; les options qu’un profil de vitesse fixe (8 pas pour Distilled) le suivent tant que vous ne les changez pas. La fenêtre laisse de côté ce que Video Producer règle lui-même : la résolution suit Brouillon ou Final, la cadence suit le preset, et les prompts et les références viennent du projet. Le menu du haut montre les options d’un autre moteur sans changer le moteur du projet, et les options de chaque moteur sont gardées : vous les retrouvez en y revenant. La section **Projet** contient les **Brouillons par plan**, de 1 à 8 : combien de prises, A, B, etc., un plan reçoit quand il n’a pas de nombre à lui (voir Brouillons par plan plus bas). **Enregistrer** garde les options avec le projet ; elles vont dans la génération de chaque plan qui tourne sur ce moteur, et l’estimation compte les pas demandés (« 8 pas au lieu de 24 : chaque prise est comptée à environ 0,33× le temps »). Une option qui ne correspond plus à son moteur (après une mise à jour du preset, par exemple) est laissée de côté et la barre le dit. La fenêtre s’ouvre aussi depuis **Production › Modifier le moteur…** et depuis le bouton en forme d’engrenage de Director IA.

### Lire l’estimation

L’estimation se trouve à droite de la barre dès qu’un moteur est choisi : une ligne courte avec le temps, la mémoire (un modèle cloud n’en a pas) et, sur une fenêtre d’au moins 1280 pixels de large, les minutes de quota ou, pour les admins, le coût. Survolez-la pour le détail. Elle suit vos modifications une demi-seconde après que vous vous êtes arrêté, une fois le projet enregistré : d’ici là elle indique « L’estimation se met à jour une fois le projet enregistré. » et, pendant le calcul, « Estimation… ». Le détail comporte ces lignes :

- **Portée.** Les plans, le nombre de prises qu’ils font ensemble et la résolution : « 2 plans · 5 prises en 832×480 ».
- **Temps.** « Temps ≈ 4 min sur MiniMax H3 (mesuré sur 3 prises) ». Il vient des prises déjà faites avec le même preset, le même moteur et la même résolution, dont la durée réelle a été mesurée : c’est la calibration. Tant qu’il n’y en a pas, on lit « Temps : — (pas encore de mesure sur MiniMax H3) » et la barre affiche « — ». Il se remplit après quelques générations, et une mesure ne sert qu’au backend qui a fait les prises.
- **Mémoire.** « Mémoire ≈ 22,5 Go, 16,0 Go libres sur Local Generation ». C’est une estimation d’après la taille des fichiers de modèle, jamais une garantie. « Mémoire : inconnue » quand elle n’a pas pu être estimée.
- **Quota.** Vos minutes GPU Video Producer mensuelles : « Quota : 5 min nécessaires, 40 min restantes sur 60 ce mois-ci », « Quota : exempté » si vous êtes exempté, et « Cloud : aucun quota GPU consommé » pour un modèle cloud, qui n’en consomme pas. Il s’affiche en **Quota GPU** dans la barre d’état quand votre admin vous a fixé une limite. Quand vos minutes sont limitées, les minutes d’une prise sont réservées à sa création et ajustées à sa durée réelle quand elle se termine ; une prise qui échoue ou qui est annulée les rend. Sans limite, ou si vous êtes exempté, aucune minute n’est réservée ni ajustée. Tant qu’un preset n’a pas été mesuré, chaque seconde de vidéo compte pour 10 secondes de GPU.
- **Coût.** Pour les admins seulement, avec un modèle cloud : « Coût ≈ » suivi du montant, ou « Coût : inconnu pour ce modèle » quand le fournisseur ne publie pas de prix.

### Blocages et avertissements

Ce qui bloque **Générer la sélection** (le bouton est désactivé et la barre affiche la première raison ; survolez-la pour les voir toutes) :

- aucune plage valide ;
- ni direction globale ni instruction locale dans la plage ;
- une instruction locale vide dans la plage ;
- aucun moteur, ou un moteur qui n’est plus disponible ;
- un preset absent ou qui ne vous est plus attribué (« Ce preset est absent ou ne vous est plus attribué. ») ;
- un profil que le moteur ne sait pas générer (« Wan 2.1 / 2.2 ne sait pas générer le profil Ref2VA : passez en FL2VA ou sur MiniMax H3. ») ;
- des fichiers de modèle que votre admin n’a pas installés (« Modèles à installer pour ce preset : … ») : demandez-les-lui ;
- un moteur cloud sans modèle (« Choisissez un modèle cloud pour ce moteur. ») ;
- un plan en Ref2VA sans aucune référence à envoyer (« “Plan 2” n’a pas de référence : Ref2VA en demande au moins une pour ce plan. ») ;
- un quota épuisé (« Quota GPU dépassé : 5 min nécessaires, 2 min restantes ce mois-ci. ») : passez à une qualité moins chère, à une plage plus courte ou à un modèle cloud ;
- un plan Ref2VA qui n’enverrait que du son (« “Plan 2” : Ref2VA demande une image ou une vidéo à côté du son du plan. ») : MiniMax H3 a besoin d’une image ou d’une vidéo pour ancrer une bande-son ;
- un plan qui envoie une piste de référence ou mixe du son sur sa prise, sur un serveur sans ffmpeg (« ffmpeg n’est pas disponible sur ce serveur : le son des plans ne peut pas être découpé. ») : demandez à votre admin.

Les boutons d’un seul plan (sur une carte du Storyboard, dans l’inspecteur, dans le visualiseur) n’attendent pas l’estimation, mais le serveur de votre admin applique les mêmes règles et la page affiche la première raison dans un message.

Ce qui avertit seulement, sans bloquer :

- une estimation de mémoire supérieure à celle du GPU : « Passera par la RAM de l’hôte, plus lent. » Les poids passent par la mémoire du serveur. La génération continue, plus lentement, et échoue si le serveur manque de mémoire pour cela (chapitre 18) ;
- le profil FL2VA sans frame liée à un plan : « “Plan 2” n’a pas de frame liée : il sera généré à partir du texte seul. » La génération continue à partir du texte, et la carte de la prise indique « texte seul ». Quand le plan a un plan précédent avec une prise terminée, une icône à côté de l’avertissement dans la barre Production, **Utiliser la dernière image du plan précédent**, lui donne une première image (chapitre 12) ;
- un moteur qui génère à partir du texte seul, comme les presets Wan (8 GB), pour un plan qui a des frames liées : « Ce moteur génère à partir du texte seul : les frames liées à « Plan 2 » ne seront pas utilisées. » La génération continue à partir du texte ;
- un plan plus long que ce que le moteur permet : « “Plan 2” dépasse la durée permise par ce moteur : il sera coupé à 15 s. » ;
- un plan dont le son est mixé sur la prise : « “Plan 2” : le son du plan sera mixé sur la prise, pas utilisé comme guide. » (chapitre 13) ;
- un plan dont le moteur ignore le son : « “Plan 2” : le son du plan est ignoré par ce moteur. » ;
- une piste de référence qui n’envoie rien : « “Plan 2” : la piste de référence A2 · Musique est muette, rien n’en est envoyé. », « … n’a aucun son sous le plan, rien n’en est envoyé. » ou, avec MiniMax H3 en Ref2VA, « … est silencieuse sous le plan, rien n’en est envoyé. »

Trois remarques n’apparaissent que dans l’infobulle de l’estimation : « La mémoire nécessaire n’a pas pu être estimée. », « Aucun temps mesuré pour ce moteur et cette résolution. » et, avec MiniMax H3 en Ref2VA, « “Plan 2” : le son du plan conditionne la génération. » Quand quelque chose bloque la génération, l’infobulle liste les avertissements sous les blocages. Une capture de l’infobulle, avec un plan dont le son est mixé sur la prise et une piste de référence muette sous lui, se trouve dans `docs/screenshots/estimate-sound.png`.

Si le son d’un plan ne peut pas être lu ou enregistré au moment de **Générer**, aucune prise n’est créée et un message nomme le plan (« “Plan 2” : un son qu’il envoie ne peut plus être lu. » ou « … le son du plan n’a pas pu être découpé ou enregistré. »).

### Générer

**Générer la sélection** (Ctrl+G) enregistre le projet et lance, pour chaque plan, autant de prises que son nombre de brouillons, chacune avec sa propre graine (ou la graine du plan, chapitre 4). Chaque plan prend le moteur, le profil et la qualité qu’il fixe dans son éditeur de plan, sinon ceux du projet et de la barre : une plage peut mêler plusieurs moteurs. Un plan est construit à partir de son instruction locale suivie des champs remplis de la direction globale, et de ses frames et références, selon le profil (voir plus bas). Si le projet n’a pas pu être enregistré, rien ne démarre (« Le projet n’a pas pu être enregistré : génération non lancée. »).

- **Brouillons par plan.** Chaque plan a son propre nombre de brouillons, de 1 à 8 : le champ **Brouillons** à côté de **Générer** sur sa carte du Storyboard, à côté de **Modifier le plan…** et du bouton « brouillons de plus » dans l’inspecteur, et dans l’éditeur de plan. Un plan qui n’a jamais reçu de nombre prend celui du projet (**Brouillons par plan** de la fenêtre Modifier le moteur, 2 par défaut). Le champ de la barre Production montre le nombre des plans visés et le donne à tous ; quand ils diffèrent, il indique **Variable**. La page envoie le nombre de chaque plan avec la requête : une plage peut mêler des plans à 1 et à 4 brouillons.
- Les boutons d’un seul plan lancent des brouillons pour ce plan seulement : **Générer** sur une carte du Storyboard, **Générer des brouillons** dans l’inspecteur et le visualiseur, et « 1 brouillon de plus » (ou « 2 brouillons de plus ») dans l’inspecteur, onglet **Prises**.
- Tant que des prises sont en cours, **Générer la sélection** est refusé avec « Une génération est déjà en cours. » La barre affiche alors la progression et **Annuler**. Un plan qui n’a aucune prise en cours peut encore être lancé par ses propres boutons.
- Votre admin limite le nombre de générations que vous pouvez avoir en cours en même temps. Les prises au-delà attendent en **En file** et démarrent d’elles-mêmes, dans l’ordre de la file, quand les autres se terminent (voir La file plus bas).

### Suivre les prises

- Chaque prise affiche son état : **En file**, **En cours** (avec l’étape et le pourcentage), **Échec**, **Annulé**, ou, une fois terminée, sa durée. La barre affiche l’étape et la progression de l’ensemble du lot, la carte du Storyboard et le bloc du plan sur la timeline affichent l’étape, le pourcentage et une barre pour leur plan (la moyenne de ses prises en cours), et **Fenêtre › Tâches en arrière-plan** compte les prises en cours (« 2 prises en cours »).
- Quand un lot se termine, un message indique combien de prises sont prêtes (« 2 prises brouillons prêtes ») avec un bouton **Voir** qui ouvre les résultats, et un autre combien ont échoué (« 1 prise en échec »). PotionUI envoie aussi les notifications « Video Producer: take ready » et « Video Producer: take failed » (leur libellé reste en anglais), si bien que vous pouvez quitter la page : les générations continuent sans elle, et les prises sont là à votre retour.
- **Annuler** sur une carte arrête cette prise. **Annuler** dans la barre, ou **Production › Annuler la génération**, arrête toutes les prises en cours (« Génération annulée » ; « Aucune génération en cours. » s’il n’y en a pas). Les minutes GPU qu’elles avaient réservées sont rendues.
- **Réessayer** sur une carte en échec lance une nouvelle prise pour le même plan, avec la même graine, la même qualité et le même moteur. La prise en échec reste dans la liste.
- **La file.** Le bouton en forme de liste de la barre Production, **Production › File de génération** (Ctrl+Alt+G) et le nombre de prises dans la barre d’état ouvrent l’onglet **File** de Director IA. Il liste vos prises en attente ou en cours dans l’ordre où elles passent : d’abord celles confiées au moteur (« Confiée au moteur », ou l’étape et le pourcentage d’une prise en cours de génération), puis celles qui attendent, numérotées (« En attente · n° 2 »). Chaque ligne donne le plan, la variante, la qualité, l’étiquette et le moteur, avec deux boutons : **Passer en tête de file** (la flèche, pour une prise en attente qui n’est pas la première : elle devient la suivante) et **Annuler**. Le haut dit combien de prises tournent sur combien peuvent tourner en même temps (« 1 / 2 en cours »), et une ligne compte vos prises en attente pour d’autres projets : tous vos projets partagent la même file. Cliquez sur le nom d’un plan pour le sélectionner. Une capture se trouve dans `docs/screenshots/generation-queue.png`.

### Profils selon le preset

Le **Profil H3 du projet** (Director IA, onglet **Direction**) dit ce qui guide la génération. Ce qu’un moteur sait faire dépend de son preset, et la page grise les profils qu’il ne sait pas générer.

| Profil | Wan 2.1 / 2.2 et ses presets (8 GB), LTX-2 / 2.3, LTX-2.5, modèles cloud | MiniMax H3 | MiniMax H3 Fast et VDN, MiniMax H3 (12 GB), MiniMax H3 Fast (12 GB) |
|---|---|---|---|
| FL2VA | Oui | Oui | Oui |
| Ref2VA | Grisé | Oui | Grisé |
| Hybrid AV | Grisé | Oui | Oui |

- Un profil grisé porte un badge tel que « Ref2VA · Hybrid AV : MiniMax H3 seulement », avec l’explication « Wan 2.1 / 2.2 ne sait pas générer Ref2VA, Hybrid AV : les images de référence (Ref2VA) et le son généré (Hybrid AV) demandent MiniMax H3. » Dans l’onglet **Références**, « Non transmis à ce moteur » vous dit que le moteur ignore les références (« Les références ne partent qu’avec le profil Ref2VA sur MiniMax H3 ; Wan 2.1 / 2.2 les ignore. »).
- **FL2VA** utilise les frames liées au plan : une frame de début et une de fin donnent une prise « première et dernière frames », une frame de début seule « première frame », et aucune frame « texte seul », avec l’avertissement ci-dessus. Le chapitre 12 montre comment prendre la première image dans le plan précédent.
- **Ref2VA** envoie à MiniMax H3 les références du plan, puis les références globales : au plus 9 images, 3 vidéos et 3 fichiers audio. Une vidéo de la famille **Guides de mouvement** est la source du mouvement du plan : MiniMax H3 reprend son mouvement dans les sujets du plan.
- **Hybrid AV** fonctionne comme FL2VA sur MiniMax H3, dont le modèle produit l’image et le son ensemble.
- Un plan peut prendre un autre profil que le projet dans son éditeur de plan (chapitre 4).

## 9. Prises et final

Une prise est une vidéo générée pour un plan. Sa vidéo est une génération PotionUI ordinaire : elle reste dans votre historique de générations (la galerie), même si vous supprimez la prise ici.

- Les brouillons sont faits à la résolution choisie par votre admin (832×480 sauf changement) ou à la plus proche que le moteur propose. La cadence d’une prise est imposée par le preset (Wan 16 i/s, MiniMax H3 24 i/s). La timeline et les exports utilisent la cadence du projet.
- Plusieurs variantes sont faites par plan : A, B, etc. Une nouvelle génération pour le même plan continue avec les lettres libres suivantes (C, D…), séparément pour les brouillons et les finals ; **Réessayer** et **Passer en final** gardent la lettre de la prise dont elles partent. Elles sont listées dans l’inspecteur, onglet **Prises** (regroupées par étiquette), et dans Director IA, onglet **Résultats**, regroupées par plan. Les deux listes ont l’interrupteur **Masquer les prises rejetées** quand il y a des prises rejetées.

### La carte de prise

- La vignette porte la lettre de la prise. Cliquez dessus pour prévisualiser la prise dans le visualiseur (« Prévisualiser la prise A ») ; **Revenir à la séquence** vous ramène.
- La première ligne donne la qualité, « Qualité brouillon », « Qualité finale » ou « Qualité finale · agrandie », pour qu’elle ne se lise pas comme l’étiquette **Finale**, puis l’étiquette de la prise (**Brouillon**, **Candidate**, **Finale** ou **Rejetée**), puis l’état (« En file », « En cours », « Échec », « Annulé ») ou, une fois terminée, la durée. Les lignes suivantes donnent le profil et la façon dont le plan a démarré (« FL2VA · première et dernière frames », « FL2VA · texte seul », « FL2VA · première frame », « Ref2VA · références »), la résolution et, pour un final, la prise dont il vient (« issue de A »), la graine (« Graine 123456 ») et le moteur qui l’a produite (le preset ou le modèle, puis le backend). **Prompt modifié** s’affiche sous la première ligne quand le plan a été modifié après la prise.
- Une prise en file n’affiche que son état (« En file ») au-dessus d’une ligne vide ; une prise en cours de génération affiche l’étape, le pourcentage et une barre de progression. Quand elle échoue, elle explique dans votre langue les causes habituelles, par exemple « La mémoire du GPU du serveur est saturée : essayez une résolution plus basse ou moins de frames. » (28 causes connues sont expliquées) ; pour toute autre cause elle affiche la raison que donne PotionUI (en anglais) ou, s’il n’en donne aucune, « La génération a échoué (invalid_request). » avec le code.
- **Comparer** met la prise à côté d’une seconde dans le visualiseur, toutes deux lues en boucle (« Choisissez une seconde prise à comparer »). **Extraire une image à la tête de lecture** (le bouton en forme d’image d’une prise terminée) enregistre une image de la prise comme première ou dernière image du plan (chapitre 12). **Détails de la génération** ouvre la fenêtre de PotionUI sur la génération. **Supprimer** demande « Supprimer cette prise ? » (« La prise A de “Plan 2” quitte la liste. La vidéo reste dans votre historique de générations. »).
- Une capture de cartes de prise, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/takes-cards.png`.
- Sur une prise en cours, **Annuler** l’arrête. Sur une prise en échec, **Réessayer** lance une nouvelle prise.
- Sous une prise qui n’est pas en cours, **Rejeter**, **Candidate** et **Finale** règlent son étiquette (voir Étiquettes).

### Étiquettes

Chaque prise a une étiquette :

- **Brouillon** : ce qu’est une nouvelle prise.
- **Candidate** : une prise qui vaut d’être gardée. Une prise faite par **Passer en final** naît candidate.
- **Rejetée** : une prise dont vous ne voulez pas. **Masquer les prises rejetées** les sort des listes sans les supprimer.
- **Finale** : la prise que le plan joue. Une seule prise d’un plan est finale.

**Finale** met la prise sur le plan : elle joue sur la timeline, le plan passe en Brouillon ou en Final (sa qualité), et la vignette de la carte affiche une coche. La prise qui était finale devient candidate. Le premier brouillon qui se termine pour un plan encore « À générer » y est mis pour vous, et un final terminé aussi : ils deviennent **Finale** d’eux-mêmes. **Rejeter** et **Candidate** sont grisés sur la prise finale (« La prise finale le reste tant qu’une autre prise du plan ne devient pas finale ») : cliquez d’abord sur **Finale** sur une autre prise. Cliquez de nouveau sur **Rejeter** ou **Candidate** pour remettre la prise en brouillon. **Édition › Annuler** et **Rétablir** gardent l’étiquette alignée sur la timeline : la prise que le plan joue après l’annulation redevient **Finale**, et un plan qui ne joue aucune prise n’a plus de finale. Dans le visualiseur, une prise prévisualisée hors montage a **Utiliser cette prise**, qui la rend finale elle aussi. **Assembler les prises choisies** (onglet Résultats) met dans le montage toutes les prises finales ; sans aucune, la page dit « Choisissez d’abord des prises pour les plans. » L’export signale un plan dont la prise est rejetée.

Les projets faits avant les étiquettes gardent leurs marques : une prise choisie est **Finale**, une prise gardée avec l’étoile est **Candidate**, une prise marquée du pouce vers le bas est **Rejetée**, les autres sont des brouillons. Une capture des étiquettes dans l’inspecteur, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/take-labels.png` ; les cartes du Storyboard et le bloc de timeline d’un plan en cours sont dans `docs/screenshots/storyboard-takes.png` et `docs/screenshots/timeline-progress.png`.

### Passer en final

**Passer en final** sur une carte brouillon (aussi le bouton d’une carte du Storyboard, **Passer la prise A en final** dans l’inspecteur, **Plan › Passer la prise en final** et Ctrl+Shift+G) ouvre la fenêtre « Passer en final · Plan 2 · A » avec la ligne « Brouillon en 832×480 · graine 123456 ». Elle propose deux voies :

- **Agrandissement** est la voie par défaut. Le moteur agrandit la prise telle quelle : l’image et le mouvement ne changent pas, et c’est le plus rapide. Les prises de Wan, LTX, MiniMax H3 Fast et VDN, MiniMax H3 (12 GB) et MiniMax H3 Fast (12 GB), et des modèles cloud passent par SeedVR2 (« SeedVR2 agrandit cette prise telle quelle : le plus rapide, le mouvement ne change pas. ») ; une prise du preset MiniMax H3 de base utilise le mode d’agrandissement de son propre preset (« MiniMax H3 agrandit cette prise avec son propre mode d’agrandissement : le mouvement ne change pas. »). Choisissez la **Résolution cible** : 720p, 1080p, 1440p ou 4K (la fenêtre part de la résolution de votre projet), puis cliquez sur « Agrandir en 1080p ».
- **Générer à nouveau en pleine résolution** génère le plan à nouveau à la plus grande résolution du moteur, avec la même graine : « plus lent, le résultat peut légèrement différer. »

Quand aucun agrandisseur ne vous est attribué, la fenêtre affiche le badge **Agrandisseur indisponible** et l’explication « Agrandir cette prise demande SeedVR2 : demandez à un administrateur de l’installer, ou générez la prise à nouveau en pleine résolution. » (le bouton **Passer en final** de cette carte de prise affiche la même phrase en infobulle), les résolutions sont grisées et seul le nouveau rendu est proposé. Une prise du preset MiniMax H3 de base n’a pas besoin de SeedVR2, tant que son preset vous est attribué. Un agrandissement prend du temps : sur une carte graphique de 12 Go, l’agrandissement en 1080p d’un brouillon Wan de 5 secondes a pris environ deux heures et demie. Une capture de cette fenêtre, dans les thèmes sombre et clair de l’interface en anglais, se trouve dans `docs/screenshots/make-final.png`.

La nouvelle prise est une prise **Final** (« Qualité finale » ou « Qualité finale · agrandie » sur sa carte) qui dit de quel brouillon elle vient (« issue de A »). Vous obtenez « Agrandissement en 1080p lancé » ou « Rendu en 1280×720 lancé », le final apparaît dans la liste de cartes quand il se termine, et il est mis sur le plan (« Version finale prête et appliquée au plan »). Un final consomme des minutes GPU comme toute prise et est vérifié par rapport à votre quota.

## 10. Assistant

L’assistant est le chat PotionUI, qui travaille dans son propre mode pour cette page, **Video Producer assistant**. Il lit votre projet et dispose de quatre outils, les actions qu’il peut lancer : écrire l’instruction d’un plan, corriger les contradictions entre la direction globale et les instructions locales, découper votre synopsis en plans, et vérifier la continuité entre les plans. Il propose et vous décidez : pour les trois outils qui écrivent ou proposent quelque chose, le chat affiche une carte d’approbation avec un aperçu, et rien ne se passe dans votre projet tant que vous n’avez pas cliqué sur **Approve**.

### Avant de commencer

- Votre admin doit configurer un modèle de langage dans PotionUI (Admin › LLM / Assistant) et vous l’attribuer. Il doit savoir appeler des outils, et un serveur de modèle local réglé pour l’assistant (le `llama-server` de llama.cpp ou Ollama, avec les réglages du guide d’administration) ou un fournisseur en ligne comme OpenAI est le choix le plus sûr : le modèle intégré à PotionUI a manqué de mémoire, ou était trop petit pour appeler les outils, sur une carte graphique de 12 Go lors de nos essais. Sans modèle, le chat indique qu’il est indisponible (voir « Si cela ne fonctionne pas » plus bas).
- L’assistant lit votre projet tel que la page le montre, mais il écrit dans le projet tel qu’il est enregistré sur le serveur. Attendez « Enregistré à » dans la barre projet avant d’approuver une modification.
- Gardez la page Video Producer ouverte pendant que vous discutez : l’assistant ne connaît votre projet que tant que la page est ouverte dessus.

### Ouvrir l’assistant

Cliquez sur **Assistant** dans la barre projet, choisissez **Fenêtre › Assistant PotionUI**, ou appuyez sur Ctrl+J (⌘J sur Mac). Le chat s’ouvre par-dessus la page. Pour une nouvelle conversation, la pastille de mode de son en-tête indique **Video Producer assistant** (le nom du mode n’est pas traduit). Une conversation garde son mode pour de bon (« Mode is fixed after the conversation starts ») : si le chat montre une conversation commencée ailleurs dans PotionUI, son en-tête dit « Started in … » et propose **start a new chat**.

Le chat est une fenêtre de PotionUI : ses boutons (**Tools**, **New chat**, **Approve**, **Reject**, **Retry**) et ses états (**Needs approval**, **Applied**, **Rejected**, **Failed**) gardent les libellés anglais de PotionUI, quelle que soit la langue de Video Producer.

### Ce que voit l’assistant

À chaque message, la page envoie à l’assistant un résumé de votre projet :

- le projet : son nom, sa version enregistrée et sa langue des prompts ;
- l’endroit où vous êtes : l’espace, la tête de lecture (et le plan qu’elle survole), votre sélection et la plage ;
- le synopsis et la direction globale : les cinq champs et le profil H3 ;
- la bible : l’étiquette visuelle et les mots de chaque fiche ;
- les plans dans l’ordre de la timeline : nom, début et fin, étape, présence d’une prise, présence d’une première et d’une dernière frame, le début de leur instruction locale et les étiquettes qu’ils distribuent ;
- les contradictions que la page signale entre une instruction locale et la direction, et les raccords de couleur et d’identité qu’elle a mesurés entre plans voisins ;
- l’état de la production : cible, qualité, progression et file.

Le résumé est du texte et il reste court : 40 plans au maximum, 800 caractères du synopsis, 240 de chaque champ de la direction et 160 de chaque instruction locale, si bien qu’un texte plus long est coupé dans ce que lit l’assistant. Il ne contient ni vos images, ni vos vidéos, ni vos prises, références, pistes audio ou scènes 3D, et l’assistant ne voit aucune image. Si vous quittez la page Video Producer, le résumé s’arrête : l’assistant dit que la page n’est pas ouverte et vous demande d’ouvrir un projet.

### Quatre demandes à essayer

Vous écrivez à l’assistant dans votre langue. Les exemples ci-dessous n’en sont que des exemples ; sélectionnez d’abord un plan et l’assistant sait duquel vous parlez.

#### Demande 1 : écrire l’instruction d’un plan

Par exemple : « Écris le prompt du plan “Les goélands” : une contre-plongée sur l’eau, à contre-jour. »

1. Le chat affiche une carte **Write shot prompt**, marquée **Needs approval**, montrant le prompt actuel et le nouveau texte (seulement le nouveau texte si le plan n’a pas encore de prompt).
2. Cliquez sur **Approve**. Le nouveau texte devient l’instruction locale de ce plan (elle est créée si le plan n’en avait pas). La page se met à jour aussitôt et dit « Prompt de « Les goélands » mis à jour par l’assistant » ; la carte passe à **Applied**.
3. Cliquez sur **Reject**, avec un motif si vous voulez, pour tout laisser comme avant.

#### Demande 2 : corriger les contradictions avec la direction

Quand l’onglet Direction de Director IA affiche **Points à vérifier · N** (par exemple « La direction globale exclut les néons. » sous une instruction qui demande du néon), demandez : « Corrige les contradictions entre ma direction et mes instructions locales. »

1. La carte **Fix conflicts** montre un bloc par plan à réécrire, avec l’ancien texte et le nouveau.
2. **Approve** applique toutes les réécritures en une seule modification, et la page dit « 2 prompts réécrits par l’assistant ». **Reject** n’en applique aucune : c’est tout ou rien.

#### Demande 3 : découper le synopsis en plans

Par exemple : « Découpe mon synopsis en plans d’environ 5 secondes. » Vous pouvez aussi raconter une histoire dans le chat et demander le découpage.

1. La carte **Split synopsis** liste les plans proposés, chacun avec sa plage de temps et « nom : début de son prompt ». Elle propose de 1 à 24 plans de 2 à 15 secondes, avec des noms de 34 caractères au plus.
2. **Approve** ne change pas encore votre projet. La page ouvre le **Storyboard** et dit « 3 plans proposés dans Storyboard ». La liste **Découpage proposé** (la même que pour **Proposer un découpage**) montre les plans : décochez ceux dont vous ne voulez pas (**Garder le plan 1**), renommez-les, puis cliquez sur **Ajouter 3 plans à la fin**. Les plans rejoignent la fin de votre film comme plans « À générer », chacun avec son instruction locale, et la page dit « 3 plans ajoutés au storyboard ».
3. **Fermer la proposition** l’abandonne. Une nouvelle proposition remplace la précédente.

#### Demande 4 : vérifier la continuité

Par exemple : « Vérifie les raccords entre mes plans et dis-moi quoi corriger. » Le bouton **Demander à l’assistant de vérifier les raccords**, dans l’onglet Direction, saisit cette demande pour vous. Celle-ci ne fait que lire votre projet : il n’y a pas de carte.

1. Quand l’assistant a répondu, la page dit « 2 raccords à vérifier » (ou « Raccords vérifiés : rien à corriger »), avec un bouton **Afficher** quand l’onglet Direction n’est pas à l’écran.
2. Dans **Director IA**, onglet **Direction**, une section **À vérifier**, avec « Assistant · 14:32 » à côté de son titre (l’heure de la vérification), liste les paires de plans voisins à regarder, sous la forme « Plan 1 → Plan 2 ». Cliquez sur une paire pour aller au plan. Sous chaque paire, une ligne dit ce qui ne va pas et une seconde comment corriger. Un point sur l’onglet **Direction** signale qu’il y a quelque chose à vérifier.
3. Ce qu’elle cherche : un plan sans prompt ; une instruction locale qui contredit la direction globale ; un plan de moins de 2 s ou de plus de 15 s ; un plan en profil FL2VA sans première image ; une instruction locale qui ne nomme pas un personnage que le plan distribue depuis la bible ; un mouvement de caméra qui change entre deux plans ; un saut de luminosité ou de température de couleur (la page les mesure sur les images, les images de raccord des plans quand ils en ont et leurs vignettes sinon, et la ligne porte le badge **Mesuré** ; chapitre 12) ; et un point de ressemblance entre deux prises. Ce dernier vient du score de ressemblance, qui reste simulé (chapitre 17), sa ligne porte donc le badge gris **Simulé** à la place. Les plans qui viennent d’une source sont ignorés.
4. **Fermer la vérification** (la croix de la section) retire la liste. Redemandez pour la rafraîchir.

### Les suggestions qui saisissent la demande à votre place

Trois endroits de la page ouvrent le chat avec une demande déjà saisie. Vous pouvez la lire, la modifier, puis appuyer sur Entrée : rien n’est envoyé à votre place.

- **Demander à l’assistant de vérifier les raccords** (Director IA, onglet Direction) : « Vérifie les raccords entre mes plans et dis-moi quoi corriger. »
- **Demander à l’assistant PotionUI**, dans la fenêtre **Bibliothèque & assistant de prompts**. La fenêtre se ferme d’abord. La demande dépend de ce dans quoi la fenêtre écrivait : « Aide-moi à écrire le prompt du plan « Les goélands ». », « Aide-moi à écrire le prompt à 5,0 s. », « Aide-moi à écrire le champ « … » de la direction globale. » ou, sans cible, « Aide-moi à écrire un prompt pour ce projet. »
- **Demander à l’assistant**, dans l’atelier Sound design, par exemple : « Aide-moi à écrire un brief sonore : Ambiance, de 0,0 s à 5,0 s. »

Si vous aviez déjà saisi quelque chose dans la zone de saisie du chat, votre texte reste et la suggestion n’est pas ajoutée. Si votre PotionUI est trop ancien pour remplir la zone de saisie, le chat s’ouvre simplement avec une zone vide et vous saisissez la demande vous-même. Les suggestions sont écrites dans la langue de l’interface.

### Ce qu’elle change, et ce qu’elle ne change pas

- Elle écrit des instructions locales (demandes 1 et 2) et propose des plans (demande 3). Elle ne lance jamais de génération, ne choisit pas de prise, ne passe pas un plan en final, n’ajoute, ne déplace ni ne supprime de plan toute seule, et ne modifie ni le synopsis, ni la direction globale, ni les références, ni les titres, ni l’audio, ni la scène 3D. Pour un champ de la direction ou pour un brief sonore, elle répond en texte seulement : copiez vous-même ce qui vous plaît.
- **Proposer un découpage** et **Production › Découper le synopsis en plans…** ne sont pas l’assistant : ils se contentent de couper le synopsis en phrases, un plan par phrase. **Production › Contrôle de continuité** vous amène à l’onglet Direction et n’appelle pas l’assistant.
- Chaque modification approuvée est une nouvelle version de votre projet : **Fichier › Historique des versions…** la montre avec le mot « Assistant ». Quand la page a appliqué la modification elle-même, **Édition › Annuler** agit dessus comme sur vos propres modifications.
- Si vous aviez saisi dans la même instruction locale sans l’avoir encore enregistrée quand vous avez approuvé, la page recharge le projet pour montrer la version de l’assistant (« Projet rechargé avec les modifications de l’assistant ») : cette saisie et votre historique d’annulation sont perdus. Attendez « Enregistré à » avant d’approuver.
- L’assistant écrit les instructions locales dans la langue des prompts du projet (chapitre 15) et vous répond dans votre langue. Il ne traduit jamais ce que vous avez écrit. Les contrôles de contradiction ne lisent que les textes écrits dans la langue des prompts.
- La liste **À vérifier** et la proposition n’apparaissent qu’une fois, quand la réponse arrive. Elles disparaissent quand vous quittez la page ou ouvrez un autre projet, et rouvrir une ancienne conversation ne les ramène pas : redemandez.
- Les messages de l’assistant disent « prompt » pour ce que ce guide appelle l’instruction locale.

### Si cela ne fonctionne pas

- **« Chat is currently unavailable ».** Aucun modèle de langage ne vous est attribué. Demandez à votre admin d’en ajouter un dans Admin › LLM / Assistant et de vous l’attribuer. (Un admin lit « No enabled LLM configurations » à la place.)
- **L’assistant répond mais n’affiche jamais de carte, ou dit qu’il ne peut pas agir.** Le bouton **Tools** de la zone de saisie du chat est désactivé : survolez-le, il indique « Tools OFF » ; cliquez dessus pour activer les outils, et vérifiez que les quatre outils du groupe Video Producer sont cochés dans sa liste. Votre admin a aussi pu les désactiver pour le modèle, ou le modèle peut ne pas savoir appeler des outils : essayez-en un autre.
- **L’assistant ne semble pas connaître votre projet, ou l’en-tête dit « Started in … ».** La conversation a été commencée dans un autre mode. Cliquez sur **start a new chat** depuis la page Video Producer.
- **L’assistant dit que la page n’est pas ouverte sur un projet.** Ouvrez un projet dans Video Producer, gardez la page ouverte et redemandez.
- **Une carte est Failed et cite `version_conflict`, `project_not_found` ou `shot_not_found`.** Le projet a été enregistré ailleurs au moment précis de l’enregistrement, a été supprimé, ou n’a plus ce plan. Laissez la page recharger le projet (**Fichier › Ouvrir…**), puis cliquez sur **Retry** sur la carte ou redemandez. L’assistant le dit lui-même dans le chat.
- **Vous avez approuvé et le chat dit « L’assistant a modifié un autre projet que celui ouvert ici. »** La réponse concernait un autre projet que celui que vous avez ouvert maintenant. Ouvrez celui-là, ou redemandez ici.
- **« Impossible de recharger le projet. Rouvrez-le pour voir les modifications de l’assistant. »** La modification de l’assistant est enregistrée, mais la page n’a pas pu la recharger : rouvrez le projet (**Fichier › Ouvrir…**).
- **La suggestion n’est pas apparue dans la zone de saisie.** Vous aviez déjà saisi un brouillon, ou votre PotionUI ne sait pas remplir la zone (il l’ouvre alors vide). Saisissez ou collez la demande.
- **Un prompt est sorti dans la mauvaise langue.** L’assistant suit la **Langue des prompts** du projet, dans **Propriétés du projet…** (chapitre 15). Changez-la, puis redemandez.
- **L’assistant se termine par une erreur de mémoire, répond en texte seul ou n’affiche jamais de carte.** Si votre admin a connecté le modèle intégré à PotionUI sur une carte graphique de 12 Go, il peut manquer de mémoire ou être trop petit pour appeler les outils. Demandez à votre admin de connecter le `llama-server` de llama.cpp, Ollama ou un fournisseur en ligne (chapitre 1).
- **Le chat affiche « Ollama returned status 400: request (… tokens) exceeds the available context size ».** Le modèle est connecté par Ollama avec son contexte par défaut, trop petit pour l’assistant. Demandez à votre admin de régler la taille de contexte (**Context Size**) de la configuration Ollama sur 16384.
- **L’assistant attend une dizaine de secondes avant chaque réponse, ou se termine parfois sans carte.** Le modèle réfléchit avant chaque appel, ou est rechargé à chaque tour. Demandez à votre admin de couper sa réflexion (**Reasoning Effort** None pour une configuration OpenAI, **Thinking Mode** Automatic ou Disabled pour Ollama) et, pour Ollama, de régler **Keep Alive**.

## 11. Prompts : bibliothèque et compositeur

La fenêtre **Bibliothèque & assistant de prompts** s’ouvre par **Fenêtre › Bibliothèque de prompts**, ou par les liens **Bibliothèque & assistant** placés près d’un texte (dans les champs de la direction globale, dans l’inspecteur pour une instruction locale et dans la fenêtre qui l’édite). Elle écrit dans une cible, indiquée sous son titre : l’un des cinq champs de la direction globale, ou une instruction locale. Ouverte depuis le menu, elle n’a pas de cible et copie le prompt dans le presse-papiers (**Copier le prompt**). La fenêtre a deux onglets, **Bibliothèque** et **Compositeur**, et un lien, **Demander à l’assistant PotionUI**, qui ferme la fenêtre et ouvre le chat PotionUI avec une demande déjà saisie (chapitre 10). Les noms, descriptions et catégories des gabarits et les choix du compositeur existent en français et en anglais et suivent la langue de l’interface ; les textes qu’ils insèrent suivent la langue des prompts du projet (chapitre 15).

- **Bibliothèque.** Cinq bibliothèques, **Intégrée**, **Personnelle**, **Projet**, **Favoris** et **Historique**, et neuf catégories (Cinéma, Caméra, Éclairage, Styles cinématographiques, Dialogue, Photographie, Son, Continuité, À éviter). Cherchez par nom, description ou mot-clé ; l’étoile marque un favori. Chaque gabarit indique les profils H3 auxquels il convient. Un gabarit peut avoir des variables, comme le sujet ou le lieu, que vous remplissez avant de l’insérer. L’**Aperçu modifiable** peut aussi être modifié à la main. **Enregistrer dans Personnelle** garde votre version, et chaque texte inséré va dans **Historique**. Un nouveau projet démarre avec les gabarits intégrés et un gabarit personnel ; **Projet**, **Favoris** et **Historique** sont vides tant que vous n’avez pas mis un gabarit en favori ou inséré un texte.
- **Compositeur.** Construit un prompt à partir de quatre parties, **Mouvement de caméra**, **Éclairage**, **Style cinématographique** et **Dialogue ou intention de jeu**, pour le profil H3 que vous choisissez (il part du profil du projet). Choisissez une option par partie, ou écrivez la vôtre dans **Autre…**, et renseignez le sujet, l’action, le lieu et l’émotion. Le **Prompt final** reste modifiable, et **Recomposer depuis les choix** le ramène à l’état d’origine. **Références nécessaires** indique si la plage a ce que le profil demande.
- **Insérer** écrit le texte dans la cible : **Compléter le texte** l’ajoute au texte existant, **Remplacer** le remplace.

Les trois profils H3 et ce que chacun demande sur la plage :

| Profil | Sens | Il demande | Moteurs |
|---|---|---|---|
| FL2VA | Continuité entre les images de départ et d’arrivée. | Des frames de départ et d’arrivée sur la plage. Sans aucune frame, les plans sont générés à partir du texte seul. | Tous. |
| Ref2VA | Préserver l’identité des références pendant l’action. | Une référence d’identité (personnage, objet). La génération suit vos références. | MiniMax H3 seulement (pas ses variantes Fast et VDN, ni les presets (12 GB)). |
| Hybrid AV | La bande son, le rythme et le dialogue guident l’image. | Une piste audio existante sur la plage (dialogue ou musique). | MiniMax H3, Fast et VDN, et les presets (12 GB). |

Le moteur, et non le tableau, a le dernier mot : la page grise un profil que le moteur choisi ne sait pas générer (chapitre 8). Les pistes audio du projet ne sont pas envoyées au moteur : MiniMax H3 produit le son lui-même.

## 12. Couleur et continuité

La continuité concerne les raccords, la coupe d’un plan au suivant. Video Producer mesure la couleur de chaque raccord, avertit quand deux plans voisins ne se raccordent pas, corrige la couleur en un clic, et peut faire démarrer un plan sur l’image exacte où le précédent s’est arrêté.

### Raccord de couleur

Une alerte n’apparaît que lorsque deux plans voisins ne se raccordent pas : « “Plan” est plus clair, plus sombre, plus chaud ou plus froid que le plan précédent ». Elle s’affiche dans Director IA (onglet **Direction**, sous **Points à vérifier**), dans le Storyboard (sous **Continuité**, et par une icône d’alerte sur la carte du plan) et dans l’inspecteur. **Raccorder** (**Raccorder la couleur** dans le Storyboard) corrige en un clic, en ajustant l’exposition et la température sur celles du plan précédent. L’onglet **Couleur** contient aussi le scope de luminance, six préréglages (Original, Lumière dorée, Matin froid, Film 35 mm, Nuit bleue, Doux) et des réglages fins (**Exposition**, **Contraste**, **Saturation**, **Température**), avec **Réinitialiser** et **À tous les plans**. Tant qu’un plan n’a pas d’image, l’onglet indique que la couleur se règle une fois le plan généré.

La mesure est faite sur de vraies images, pour chaque plan qui en a une. Le projet de départ n’en a pas encore, et le Storyboard indique alors « Aucun raccord à calculer : les plans n’ont pas encore d’image. » Un pourcentage de ressemblance entre deux plans générés peut aussi apparaître dans les alertes (« Identité à vérifier entre … et … (similarité 78 %) ») : il est simulé (chapitre 17). La couleur, elle, est réelle.

### Raccord auto

**Raccord auto**, dans l’onglet **Couleur** de l’inspecteur, corrige la couleur d’une prise d’après une image d’**Ancre** plutôt que d’après le plan précédent. L’ancre proposée est l’image de début du plan (son image clé), puis une autre image clé du plan, une référence image propre au plan, la dernière image du plan précédent et enfin une référence du projet : raccorder chaque plan au précédent accumule la dérive, ce que rappelle la page quand vous choisissez cette ancre. La liste **Ancre** reste modifiable ; changer d’ancre refait la mesure.

1. La page mesure, en CIELAB, la moyenne et l’écart type de la luminance et des deux axes de couleur sur l’ancre et sur trois images de la prise (à 15, 50 et 85 % du plan).
2. Elle en tire un transfert statistique (méthode de Reinhard, en Lab), l’applique avec l’**Intensité** choisie (80 % par défaut) et affiche l’écart avant et après, en ΔE, avec le sens de la dérive (« prise plus chaude », « prise plus sombre »…). Les vignettes **Ancre**, **Prise** et **Raccordée** permettent de comparer.
3. À l’export, le raccord est cuit en LUT 3D (33³ points, fichier `.cube`) appliquée par ffmpeg avant le cadrage et avant les réglages fins. Le visualiseur et les vignettes montrent la même LUT (WebGL, ou calcul sur la page quand WebGL manque), pas un filtre CSS.

Si la prise du plan change, le raccord n’est plus appliqué et l’onglet demande de **Mesurer à nouveau**. **Retirer** supprime le raccord. **Réduire le scintillement à l’export** ajoute le filtre `deflicker` de ffmpeg au plan ; il n’agit que dans la vidéo exportée.

### Ce que regarde la mesure

Pour chaque paire de plans voisins, la page compare la fin du premier avec le début du second :

- pour le plan précédent, l’image qui est sa **Dernière image** s’il en a une, sinon sa vignette ;
- pour le plan, l’image qui est sa **Première image** s’il en a une, sinon sa vignette.

Toute image que vous avez placée comme première ou dernière image compte, pas seulement celles faites dans ce chapitre. La vérification de continuité de l’assistant (chapitre 10) marque d’un badge **Mesuré** les points que la page a mesurés ; survolez-le pour voir ce qui a été mesuré : « Mesuré par cette page sur les images de raccord : dernière image du plan précédent, première image de celui-ci », ou « Mesuré par cette page sur les vignettes des plans ». Le point de ressemblance garde le badge gris **Simulé**.

### Faire démarrer un plan sur le précédent

Une **image de raccord** est une image tirée d’une prise et utilisée comme première ou dernière image d’un plan. Avec le profil FL2VA, une prise démarre sur sa première image (chapitre 8) : donner à un plan la dernière image du plan précédent fait se rejoindre les deux plans sans saut.

**Utiliser la dernière image du plan précédent** est proposé à cinq endroits :

- sous chaque alerte de Director IA, onglet **Direction**, section **Points à vérifier**, à côté de **Raccorder** ou **Voir les prises** ;
- sous chaque alerte du Storyboard, section **Continuité**, à côté de **Raccorder la couleur** ;
- sur les lignes de la vérification de l’assistant qui disent qu’un plan n’a pas de première image (chapitre 10) ;
- dans la section **Images clés** de l’inspecteur, onglet **Plan**, qui montre la **Première image** et la **Dernière image** du plan (« Aucune » quand elle est vide) et un bouton du même nom ;
- sous forme d’icône à côté de l’avertissement de la barre Production qui dit que le plan sera généré à partir du texte seul (chapitre 8).

Quand vous cliquez :

1. La page enregistre le projet et demande au serveur l’image de fin de la portion montée du plan précédent : la dernière image que ce plan montre dans votre montage, à son point d’entrée plus sa durée, tirée de la prise placée sur lui (sa prise finale ou choisie) ou de sa vidéo importée. Après une image fixe, c’est l’image elle-même. Le bouton affiche « Extraction de l’image… » pendant ce temps.
2. L’image est enregistrée dans votre bibliothèque au format PNG, ajoutée aux médias du projet et utilisée comme **Première image** du plan, avec toute son influence, au début du plan. Vous la voyez dans la rangée **Frames** de la timeline et dans l’inspecteur. La page dit « Dernière image de “Plan 1” utilisée comme première image de “Plan 2” » avec un bouton **Annuler**.
3. Rien n’est généré et les prises que vous avez déjà ne changent pas : la prochaine prise que vous générez pour le plan démarre sur cette image. L’image ne fait que guider la génération ; elle n’est pas dessinée dans une vidéo exportée.

Si le plan a déjà une première image, une fenêtre demande « Remplacer la première image ? » (« “Plan 2” a déjà une première image. La nouvelle la remplace ; vous pourrez annuler. »). **Remplacer** l’échange et **Garder l’actuelle** ne change rien. L’image remplacée reste dans les médias du projet. **Annuler** dans le message, ou **Édition › Annuler**, ramène l’image précédente.

L’action est grisée, avec l’explication « “Plan 1” n’a encore ni prise ni vidéo. », tant que rien n’est placé sur le plan précédent, et elle n’est pas proposée pour le premier plan du film.

### Les nouveaux plans s’ouvrent sur le précédent

Quand vous ajoutez un plan après un autre (**Plan**, **Nouveau plan** et **Insérer un plan après** dans le Storyboard, la commande **Nouveau plan**, ou **Ajouter N plans à la fin** pour un découpage, le vôtre ou celui de l’assistant), le nouveau plan prend comme **Première image** l’image de fin de la portion montée du plan précédent, comme si vous aviez cliqué sur **Utiliser la dernière image du plan précédent**. La page dit « Première image de “Plan 3” : la dernière image de “Plan 2” », avec **Annuler**. Couper un plan à la tête de lecture et dupliquer un plan ne le font pas.

- **Le plan précédent n’a encore ni prise ni vidéo.** Rien n’est posé. Dès qu’une prise arrive sur lui, le raccord propose l’image : « “Plan 2” a maintenant une image : sa dernière image peut ouvrir “Plan 3” », avec **Utiliser la dernière image du plan précédent**, dans Storyboard › **Continuité**, dans Director IA › **Points à vérifier** et sur la vignette du plan. La proposition reste tant que le nouveau plan n’a pas de prise à lui.
- **Vous gardez la main.** L’image est une première image ordinaire : changez-la ou retirez-la dans l’éditeur de plan (**Première image**) ou dans l’inspecteur.
- **Le plan précédent change ensuite** (une autre prise placée, une autre finale, un rognage de son point d’entrée ou de sa durée, les plans réordonnés) : la première image n’est jamais remplacée dans votre dos. Le raccord dit « La première image de “Plan 3” est périmée : “Plan 2” a changé depuis que sa dernière image a été reprise » et son bouton devient **Reprendre la nouvelle dernière image**, qui prend aussitôt la nouvelle image, sans demander de confirmer le remplacement. Une première image que vous avez choisie vous-même n’est jamais signalée périmée.
- **Pour le désactiver**, ouvrez **Fichier › Propriétés du projet…** et décochez **Ouvrir chaque nouveau plan sur le précédent**. L’option appartient au projet et elle est active dans tous les projets, anciens compris. Désactivée, les nouveaux plans commencent sans première image et le raccord ne propose rien ; les premières images déjà reprises disent toujours quand elles sont périmées.
- **Un moteur qui génère à partir du texte seul** (les presets Wan 12 Go et 8 Go en texte vers vidéo) n’utilise pas les premières images. Les propriétés du projet le disent sous l’option, et l’estimation prévient pour chaque plan : « Ce moteur génère à partir du texte seul : les frames liées à “Plan 3” ne seront pas utilisées. »

### Extraire une image à la tête de lecture

Pour un autre moment que la dernière image, utilisez **Extraire une image à la tête de lecture**, le bouton en forme d’image de la carte d’une prise terminée (inspecteur, onglet **Prises** ; Director IA, onglet **Résultats**). Son infobulle dit « Enregistre l’image de cette prise sous la tête de lecture comme première image (première moitié du plan) ou dernière image (seconde moitié) ». Placez la tête de lecture sur le plan, au moment voulu, puis cliquez dessus :

- l’image est prise dans cette prise à la position de la tête de lecture dans le plan (pour la prise que le plan joue, son point d’entrée est pris en compte) ;
- dans la première moitié du plan elle devient la **Première image**, dans la seconde la **Dernière image** ; une tête de lecture hors du plan compte pour son début ou sa fin ;
- la page dit « Image à 2,5 s utilisée comme première image de “Plan 2” » (ou « dernière image »), et demande d’abord « Remplacer la dernière image ? » s’il y en a une.

### Autres contrôles

L’assistant peut lancer davantage de contrôles à la demande : plans sans prompt, contradictions avec la direction globale, durées hors de 2 à 15 s, plans FL2VA sans première image et mouvements de caméra qui changent entre deux plans, avec les points de couleur ci-dessus. Sa réponse est une seconde liste **À vérifier** dans l’onglet Direction (chapitre 10).

## 13. Audio et sous-titres

L’audio vit dans des pistes, chacune avec un rôle : Dialogue, Musique, Ambiance ou SFX. **Audio › Ajouter une piste audio**, **Audio › Importer un son de la bibliothèque…** et **Audio › Importer un son depuis l’ordinateur…** font entrer des sons ; **Audio › Console de mixage** affiche la console. Dans la console, chaque tranche a un rôle, des effets (**Égaliseur**, **Compresseur**, **Filtre** ; **+ effet** en ajoute un), des envois vers les bus de réverbération et de délai (R et D), un panoramique, un fader (double-cliquez dessus pour revenir à 0 dB), un vumètre, **M** et **S** et un bouton d’automation ; les bus auxiliaires et le **Master** suivent. Les pastilles du haut ne montrent qu’un rôle. **Voix et dialogues…** et les commandes de sound design (**Ambiance…**, **Bruitage…**, **Texture…**, **Impact…**, **Intention musicale…**) ouvrent l’**Atelier Sound design**, qui est simulé (chapitre 17). Le texte d’un dialogue, lui, est réel : il alimente les sous-titres, avec les titres de la timeline (chapitre 14).

### Pistes : ajouter, supprimer

**Audio › Ajouter une piste audio**, le menu **Ajouter** de la timeline et **+ Piste audio** dans la console ajoutent une piste audio en bas. Les pistes sont nommées **A1**, **A2**… selon leur place : supprimez A2 et la piste qui était A3 devient A2. Leurs noms (**Dialogue**, **Musique**…) ne changent pas.

Pour supprimer une piste, sélectionnez-la (clic sur son nom dans la timeline ou sur sa tranche dans la console) et cliquez sur **Supprimer la piste A2** en bas de l’inspecteur, ou appuyez sur Suppr ; ou faites un clic droit sur son nom dans la timeline et choisissez **Supprimer la piste…**. Une fenêtre demande d’abord et dit ce qui part avec elle, par exemple « A2 · Musique contient 3 clips audio. Ils sont supprimés avec la piste. Annuler les rétablit. » **Supprimer la piste** supprime la piste et ses clips audio ; **Édition › Annuler** (Ctrl+Z) rétablit les deux. La dernière piste peut aussi être supprimée : un fichier audio ajouté ensuite reçoit une nouvelle piste pour son rôle. Captures, dans les thèmes sombre et clair de l’interface anglaise : le menu de piste sur la timeline dans `docs/screenshots/timeline-tracks.png`, la confirmation dans `docs/screenshots/lane-delete.png`.

### Muet et solo

**M** rend une piste muette, **S** la met en solo, sur la timeline comme dans la console ; la piste vidéo **V1** les a aussi, pour le son des vidéos des plans. Une seule règle décide de ce que vous entendez, dans le visualiseur comme dans la vidéo exportée :

- Un clip audio est entendu quand sa piste n’est pas muette et, si une piste est en solo (V1 comprise), que sa piste est aussi en solo.
- Le son d’un plan est entendu quand ni V1 ni le plan ne sont muets et, si une piste est en solo, que V1 est aussi en solo. **Couper le son du plan** (inspecteur, **Son du plan**) ou le haut-parleur du plan sur la timeline coupe un seul plan.
- Muet l’emporte sur solo. Mettez V1 et A1 en solo pour n’entendre que les plans et les dialogues.

L’inspecteur d’un plan dit pourquoi son son n’est pas entendu : « La piste V1 est muette… » ou « Une piste audio est en solo… ». Une capture de **Son du plan** avec une piste audio en solo est dans `docs/screenshots/shot-sound.png`.

### Le son qui accompagne la génération

Deux choses envoient du son avec la génération d’un plan :

- **Les références sonores** (Director IA › Références, famille **Son** ; ou **Ajouter un son** dans l’éditeur de plan) : une voix, une musique ou une ambiance, globale ou propre à un plan, qu’un plan peut exclure comme toute référence (chapitre 4).
- **Les pistes de référence** : les pistes audio que vous cochez **Référence pour la génération**, avec l’interrupteur de l’inspecteur de la piste ou le bouton **Réf.** de sa tranche dans la console. Une petite icône d’étincelles à côté du nom de la piste, sur la timeline, les signale. À chaque génération, la portion de la piste sous le plan est découpée sur le serveur, ses clips mixés avec leur gain, leurs fondus et le volume de la piste, du silence là où rien ne joue, et envoyée avec le plan. Un plan peut écarter une piste avec **Exclure** dans son éditeur de plan. Une piste muette, ou écartée par un solo, n’envoie rien, pas plus qu’une piste sans clip sous le plan : l’estimation le dit. Avec MiniMax H3 en Ref2VA, une piste silencieuse sous le plan (son passage le plus fort à −60 dB ou moins) n’est pas envoyée non plus, et les autres sons prennent sa place.
- **Les clips de référence** : chaque clip audio a son propre interrupteur **Référence pour la génération** dans son inspecteur. Laissé tel quel, le clip suit sa piste. Réglé, il l’emporte sur la piste : un clip activé est envoyé même depuis une piste qui n’est pas une piste de référence, un clip désactivé n’est jamais envoyé, même depuis une piste de référence. **Suivre la piste A1** rend le choix à la piste. Une icône d’étincelles devant le nom d’un clip, sur la timeline, signale chaque clip envoyé. Seuls les clips envoyés, sous le plan, sont découpés, mixés, mesurés pour le silence et envoyés ; une piste de référence dont tous les clips sous le plan sont désactivés n’envoie rien et ne dit rien.

Ce que le moteur fait de ce son dépend de lui, et l’éditeur de plan, la carte du Storyboard et l’estimation disent lequel s’applique :

| Moteur | Ce qui se passe | Ce que dit la page |
|---|---|---|
| MiniMax H3 avec le profil Ref2VA | Le son est une référence audio : la génération le suit (au plus 3 sons par plan, d’abord les références du plan, puis les pistes de référence, puis les références globales ; un même fichier n’est envoyé qu’une fois). La portion de chaque piste est découpée avec la **Marge** de la barre Production avant et après le plan. Un son ne peut pas être la seule référence : ajoutez une image ou une vidéo. | « Conditionne la génération : MiniMax H3 suit ce son. » |
| LTX-2, LTX-2.5, MiniMax H3 hors Ref2VA | Les pistes et les références sonores sont mixées en un seul fichier exactement aussi long que le plan (sans marge : le son reste synchrone avec l’image) et posées sur la prise. L’image n’en est pas tirée. | « Sera mixé sur la prise, pas utilisé comme guide. » |
| Wan, modèles cloud et autres moteurs | Rien n’est envoyé. Les pistes jouent toujours dans votre montage et dans la vidéo exportée. | « Ignoré par ce moteur : le son reste seulement dans le montage. » |

Les fichiers découpés sont enregistrés une fois par plan et par génération dans votre bibliothèque, en WAV nommés d’après le plan (« vp-sound-shot-01-a1.wav », « vp-sound-shot-01-mix.wav » ; avec MiniMax H3 en Ref2VA, les références sonores sont aussi réenregistrées au taux que lit le modèle, « vp-sound-shot-01-sound1.wav »), pour que tous les brouillons du plan utilisent le même son. Une prise faite avec un son mixé le joue dans le visualiseur comme toute prise. Captures, en thèmes sombre et clair de l’interface anglaise : les références **Son** dans `docs/screenshots/sound-references.png`, l’éditeur de plan dans `docs/screenshots/shot-editor-sound.png`, les pistes de référence dans la console et l’inspecteur dans `docs/screenshots/lane-reference.png`, les cartes du Storyboard dans `docs/screenshots/sound-cards.png`.

### Découper un son en tranches

Pour choisir quelles secondes d’un long son accompagnent la génération, découpez-le en tranches. Sélectionnez un clip audio, réglez **Durée** dans la section **Tranches** de son inspecteur (5 s par défaut, de 1 à 60 s ; la page garde cette durée pour tous les clips jusqu’à ce que vous la rechargiez, et elle n’est pas enregistrée dans le projet) et cliquez sur **Découper**, ou passez par **Montage › Découper le clip en tranches de 5,0 s** (Ctrl+Shift+B). Le clip devient des clips consécutifs de cette durée sur la même piste, le dernier plus court (ou plus long de 0,1 s au plus, pour ne pas laisser de miette) : chaque tranche reprend le fichier là où la précédente s’arrête, avec le même gain et le même réglage **Référence pour la génération** ; il n’y a pas de fondu aux coupes intérieures, et les fondus du clip restent sur sa première et sa dernière tranche. Un clip donne au plus 200 tranches à la fois. Chaque tranche a ensuite son propre interrupteur.

**Recoller** (ou **Montage › Recoller les tranches**, Ctrl+Alt+B) rassemble les tranches du clip sélectionné : les clips du même fichier sur la même piste qui se suivent, sur la timeline comme dans le fichier (à 0,025 s près). Les tranches dont le réglage **Référence pour la génération** ou le gain diffère restent à part, pour que recoller ne change jamais ce que vous entendez ni ce qui accompagne une génération : douze tranches dont la 3e, la 7e et la 8e sont désactivées donnent cinq clips. Un clip recollé garde le fondu d’entrée de sa première tranche et le fondu de sortie de sa dernière. **Édition › Annuler** (Ctrl+Z) annule un découpage ou un recollage.

**Découper sur les plans** (dans la section **Tranches** d’un clip audio, ou d’une piste audio pour tous ses clips ; aussi **Montage › Découper sur les plans**) coupe aux bornes des plans de V1 au lieu de toutes les N secondes : une tranche par plan qui recouvre le clip, qui commence et finit exactement avec son plan, selon les mêmes règles que plus haut (même endroit du fichier, gain, piste et réglage **Référence pour la génération**, pas de fondu aux coupes intérieures, fondus extérieurs gardés, 200 tranches au plus par clip). Deux bornes à moins de 0,1 s l’une de l’autre ne font qu’une coupe, à la seconde : l’arrondi des temps des plans (quelques centièmes de seconde entre deux plans) ne laisse pas de miette, et un plan de moins de 0,1 s n’a pas de tranche à lui, son son part avec la tranche du plan qui le précède. Un espace entre deux plans, et la partie d’un clip qui dépasse le dernier plan, deviennent des tranches à part, pour que l’interrupteur de la tranche d’un plan n’agisse que sur ce plan et qu’un plan ajouté plus tard à la fin trouve sa tranche prête. Un clip qui commence ou finit à moins de 0,1 s d’une borne n’est pas coupé là. **Édition › Annuler** annule en une fois tout le découpage, d’un clip ou d’une piste.

### Vos fichiers audio

Les quatre pistes d’un nouveau projet sont vides. **Audio › Importer un son de la bibliothèque…** et **Audio › Importer un son depuis l’ordinateur…** font entrer vos propres fichiers audio, et vous pouvez déposer des fichiers audio sur une piste (chapitre 6). La console les joue pour de vrai : les faders, muet et solo, panoramique, égaliseur, compresseur, filtre et envois agissent sur le son que vous entendez, les vumètres le montrent, et les clips de la timeline dessinent la forme d’onde du fichier. Les sons que l’atelier Sound design prépare sont encore synthétisés par votre navigateur (WebAudio).

## 14. Exports

**Fichier › Exporter la vidéo…** (Ctrl+E) ouvre **Exporter et partager**, avec trois onglets : **Vidéo**, **Vers un autre logiciel** et **Sous-titres**. **Fichier › Exporter vers un autre logiciel…** (Ctrl+Shift+E) et **Fichier › Exporter les sous-titres…** ouvrent les deux autres. Avant l’export, la fenêtre signale les plans qui ne sont pas encore en version finale, les plans qui utilisent une prise que vous avez marquée **Rejeter** et les contradictions de direction non résolues. Chaque export commence par enregistrer le projet ; si cela échoue, la page dit « Le projet n’a pas pu être enregistré : rien n’a été exporté. » et n’exporte rien.

### Vidéo

Choisissez un format, une résolution et l’étendue, puis cliquez sur **Exporter**.

- **Format.** Deux formats sont réels. **Web · H.264 MP4** a le format d’image de votre projet. **Réseaux sociaux · H.264 vertical** est toujours en 9:16 : les plans remplissent l’image et sont recadrés autour de leur centre. **Fichier maître · ProRes 422** et **Archive · H.265** restent simulés et portent le badge **Simulé**.
- **Résolution.** 720p, 1080p ou 4K ; la fenêtre démarre sur la résolution de votre projet. Le petit côté de l’image fait 720, 1080 ou 2160 pixels. Pour un projet 16:9, une vidéo web fait 1280×720, 1920×1080 ou 3840×2160, et une vidéo pour les réseaux sociaux 720×1280, 1080×1920 ou 2160×3840.
- **Étendue.** Les vidéos web et réseaux sociaux rendent toujours la **Séquence entière**. **Plage** est grisée, et quand vous avez tracé une plage la fenêtre dit « Les exports web et réseaux sociaux rendent la séquence entière. »
- **Stems audio par rôle.** L’interrupteur est simulé et ne change rien aux vidéos web et réseaux sociaux.
- **Son.** **Niveau** : **Tel que mixé** (par défaut), **Web et réseaux · −14 LUFS** ou **Diffusion EBU R128 · −23 LUFS**. Le serveur mesure d’abord le mixage (`loudnorm`, premier passage), puis applique un seul gain au mixage entier (second passage, mode linéaire) : la dynamique ne change pas, et le gain s’arrête avant que les crêtes vraies dépassent −1 dBTP, quitte à rester un peu sous la cible. **Fondu enchaîné entre clips voisins** : **Aucun**, 0,25 s, 0,5 s ou 1 s. Deux clips d’une même piste qui se touchent (à une demi-image près) se fondent l’un dans l’autre (`acrossfade`, puissance constante), centrés sur la coupe et pris dans la matière qui dépasse de chaque côté, sans décaler le second. Ces deux réglages sont enregistrés dans le projet. La fenêtre indique aussi combien de plans ont un raccord couleur cuit en LUT, et ceux dont la prise a changé depuis.

Sous les choix, la fenêtre montre le nom du fichier (le nom du projet dont les espaces deviennent des tirets bas, puis la résolution, par exemple `Aube_sur_le_port_1080p.mp4`), sa cadence et son format d’image et la note « Rendu sur le serveur avec ffmpeg ».

Ce que contient la vidéo :

- Les plans dans l’ordre du projet, avec leur **Raccord auto** (LUT 3D), les réglages de **Couleur** (exposition, contraste, saturation, température) et les fondus de chaque plan. Un plan sans fichier que le serveur peut trouver, et chaque vide entre deux plans, est noir et silencieux. Une image placée comme plan est tenue pendant la durée du plan.
- Le son de la vidéo propre à chaque plan, avec les fondus du plan, sauf si le plan ou la piste V1 est muet ou qu’une autre piste est en solo, et vos pistes audio avec leur gain, le fader de leur piste, muet et solo, et leurs fondus (la règle du chapitre 13, la même que dans le visualiseur). Les pistes sont additionnées telles quelles ; le niveau final et les fondus enchaînés ne s’appliquent que si vous les choisissez dans **Son**.
- Pas dans la vidéo : les titres et les marqueurs, les sous-titres (toujours un fichier à part, voir plus bas), et le panoramique, l’égaliseur, le compresseur, le filtre, les envois, l’automation et le fader master de la console. Ce que vous entendez dans la console avec eux n’est pas ce que contient le fichier.

Si votre admin n’a pas installé ffmpeg sur le serveur, l’onglet Vidéo dit « ffmpeg est absent du serveur : les exports web et réseaux sociaux en ont besoin. » (avec un lien **Lire le guide** pour un admin, et « Demandez à un administrateur de l’installer. » pour les autres) et **Exporter** est désactivé pour les formats web et réseaux sociaux.

### Suivre l’export

L’export se fait sur le serveur, en arrière-plan. La fenêtre montre une carte avec le nom du fichier, son état (**En file**, **Rendu en cours**, **Prêt**, **Échec** ou **Annulé**), l’étape en cours, un pourcentage et une barre de progression :

| Étape | Ce qui se passe |
|---|---|
| En file d’attente | Un autre export tourne sur le serveur, qui n’en fait qu’un à la fois. |
| Assemblage des plans | Les plans sont mis bout à bout, avec leur couleur et leurs fondus. |
| Mixage de l’audio | Le son est mixé. C’est le même passage que l’assemblage : l’étape change à 50 %. |
| Conversion en MP4 | Le MP4 final est fabriqué. Le pourcentage passe de 70 à 95 % pendant cette étape. |
| Enregistrement dans votre bibliothèque | Le MP4 est copié dans votre bibliothèque. |

- **Annuler** arrête un export en file ou en cours (« L’export a été annulé. »), à n’importe quelle étape.
- Vous pouvez fermer la fenêtre ou quitter la page : l’export continue. Fenêtre fermée, la page continue de le suivre et affiche un toast avec **Télécharger** quand il est prêt. PotionUI envoie la notification « Video Producer: export ready » (ou « Video Producer: export failed » ; leur libellé reste en anglais), et quand vous rouvrez **Exporter et partager** la carte est de retour.
- Un projet n’a qu’un export à la fois (« Un export de ce projet est déjà en cours. »).
- Quand il est prêt, la carte dit « Aube_sur_le_port_1080p.mp4 est prêt » avec sa taille, et propose **Télécharger** et, quand votre PotionUI peut l’afficher, **Afficher dans la bibliothèque**, qui ouvre votre bibliothèque sur les vidéos. Le MP4 est aussi dans votre bibliothèque comme n’importe quelle vidéo : vous pouvez l’importer dans un projet (chapitre 6).
- Un export en échec dit ce qui a échoué (« ffmpeg n’a pas pu assembler la vidéo. », « La vidéo n’a pas pu être convertie. » ou « La vidéo n’a pas pu être enregistrée dans votre bibliothèque. ») et, en dessous, le message technique du serveur (chapitre 18).

### Exports précédents

Sous la carte, **Exports précédents** liste d’abord l’export en cours, avec son état, puis les exports antérieurs du projet : format et résolution, état, quand il s’est terminé et sa taille, avec une icône de téléchargement (**Télécharger <fichier>**) et une icône corbeille (**Supprimer <fichier>**). La suppression demande « Supprimer cet export ? » (« <fichier> est retiré du dossier d’export. La copie de votre bibliothèque reste. ») : **Supprimer** ou **Le garder**. Sans export, la liste dit « Aucune vidéo exportée pour ce projet. »

Les fichiers MP4 sont gardés dans votre stockage PotionUI, dans un dossier `video_producer/exports/`, jusqu’à ce que vous les supprimiez. Votre admin fixe un budget de taille pour ce dossier, par utilisateur. Quand il est atteint, vos plus anciens exports terminés sont supprimés pour faire de la place, et si cela ne suffit pas l’export est refusé : « Le dossier d’export est plein : supprimez d’anciens exports et réessayez. » La copie de votre bibliothèque ne compte pas dans ce budget et reste quand un export est supprimé.

### Vers un autre logiciel

Trois fichiers, fabriqués par le serveur à partir de votre projet enregistré : **FCPXML** (`.fcpxml`), **OpenTimelineIO** (`.otio`) et **EDL CMX 3600** (`.edl`). Cliquez sur une carte, lisez sa note et le début du fichier, puis cliquez sur **Télécharger** suivi du nom du fichier, qui vient du nom du projet (par exemple « Télécharger Aube_sur_le_port.fcpxml »). La page dit « <fichier> téléchargé ».

- **FCPXML.** « Séquence V1 avec les prises retenues, noms de plans et points d’entrée. » Une rangée vidéo, avec un plan sans média en vide. Pas d’audio.
- **OpenTimelineIO.** « Vidéo et pistes audio par rôle ; lisible par Resolve, Premiere (plugin) et Nuke Studio. » La même rangée vidéo, et une piste audio par piste de la console, nommée **A1**, **A2**… comme sur la timeline, avec la position, le rôle et le gain de chaque clip. Les clips audio ne portent aucun fichier.
- **EDL.** « Liste de montage universelle (V1 seulement), pour l’étalonnage ou le conformage. » Un événement par plan, avec son nom et son fichier média ; un plan sans média est sur une bobine noire (BL).

Ces fichiers ne portent que le montage : ni fondus, ni réglages de couleur, ni titres, ni fichiers audio.

**Chemins des médias.** Les fichiers pointent vers les vrais fichiers média de vos plans, tels que le serveur les range : « Les chemins des médias sont les vrais fichiers du serveur, tirés du projet enregistré. » L’aperçu affiché dans la fenêtre liste des noms de fichiers, mais le fichier que vous téléchargez contient les chemins complets sur le serveur. Si votre logiciel de montage tourne sur un autre ordinateur, ces chemins n’y existent pas : mettez les vidéos de vos prises (téléchargez-les depuis votre galerie) et vos médias importés sur cet ordinateur et reliez-les de nouveau dans votre logiciel.

**Importer.** Un logiciel de montage qui lit le FCPXML 1.10 importe le `.fcpxml` : le projet apparaît dans un événement nommé « Video Producer ». Le fichier `.otio` s’ouvre dans les logiciels cités ci-dessus et dans les autres qui gèrent OpenTimelineIO. Le `.edl` est lu par les logiciels de montage et d’étalonnage qui gèrent le format CMX 3600. Les menus varient d’un logiciel à l’autre et d’une version à l’autre : suivez la commande d’import du vôtre.

### Sous-titres

Un fichier SRT construit à partir du texte des dialogues (les répliques écrites pour les clips audio, avec le nom du personnage devant : « Mara : Bonjour ») et des titres de la timeline (le titre, puis son sous-titre sur une seconde ligne), dans l’ordre du temps. L’onglet liste les répliques avec leurs temps (« Aucun dialogue ni titre à sous-titrer. » s’il n’y en a pas) et propose **Télécharger** suivi du nom du fichier, qui se termine par `.srt`. Les sous-titres ne sont jamais incrustés dans la vidéo : chargez le SRT dans votre lecteur ou votre logiciel de montage.

## 15. Langue

Video Producer existe en anglais et en français. Choisissez **English** ou **Français** dans **Video Producer › Préférences…**, réglage **Langue**, ou cliquez sur le rappel `EN` ou `FR` à gauche de la barre d’état, qui ouvre la même fenêtre. Le changement est immédiat et n’est enregistré que pour vous, sur le serveur ; si l’enregistrement échoue, un message indique que la langue n’a changé que pour cette session. Tant que vous n’avez pas choisi, la page suit la langue de votre navigateur (français s’il est en français, anglais sinon).

La fenêtre **Préférences** a cinq autres réglages : **Langue des prompts** (voir plus bas), **Qualité d’aperçu** (**Meilleures performances**, **Équilibrée** ou **Meilleure qualité**, sans effet), **Magnétisme par défaut**, **Guides de cadrage** et **Raccourcis à une touche** (chapitre 16). Sauf **Langue des prompts**, enregistrée avec le projet, ils valent pour la session en cours et ne sont pas enregistrés.

Ce qui est traduit : les menus, les fenêtres, les boutons, les infobulles, les messages, les noms donnés aux nouveaux éléments (par exemple un nouveau plan ou une nouvelle piste), la bibliothèque de prompts avec ses gabarits, ses catégories et les choix du compositeur, et la façon d’écrire les nombres et les durées. Ce qui n’est jamais traduit, c’est le contenu de votre projet : vos propres textes (synopsis, direction, prompts, noms et titres que vous avez saisis, nom du projet) et le projet de départ, qui est créé une fois et n’est pas traduit ensuite. Les termes du produit comme Director IA, Storyboard, Control video ou FL2VA sont les mêmes dans les deux langues.

### Langue des prompts

Chaque projet a sa propre **Langue des prompts**, anglais ou français. C’est la langue des textes envoyés aux modèles, la direction globale et les instructions locales, et elle ne dépend pas de la langue de l’interface. C’est l’anglais par défaut.

Changez-la dans **Propriétés du projet…** (le réglage dit « Langue de la direction et des prompts envoyés aux modèles. La changer ne réécrit pas les textes existants. ») ou dans **Préférences…** (le réglage dit « S’applique au projet courant »). Elle est enregistrée avec le projet. Un nouveau projet démarre toujours en anglais, quelle que soit la langue de l’interface ou du projet ouvert.

Ce qu’elle change :

- **Le projet de départ.** Sa direction globale et ses instructions locales sont écrites en anglais, même quand l’interface est en français. Son nom, son synopsis, les noms de ses plans, son titre et son marqueur suivent la langue de l’interface.
- **La bibliothèque de prompts.** Le texte que les gabarits intégrés insèrent, leurs variables (le sujet, le lieu, etc.) et les valeurs par défaut de ces variables sont écrits dans la langue des prompts. Les noms, descriptions et catégories des gabarits suivent la langue de l’interface.
- **Le compositeur.** Le **Prompt final** est composé dans la langue des prompts. Les choix sur lesquels vous cliquez gardent la langue de l’interface.
- **Les contrôles de direction.** Les contrôles qui lisent vos textes utilisent les règles de la langue des prompts : les contradictions entre la direction globale et une instruction locale (par exemple une direction qui exclut le néon et une instruction qui en demande). Un texte écrit dans l’autre langue n’est pas contrôlé.
- **L’assistant.** Il écrit chaque instruction locale, réécriture et plan proposé dans la langue des prompts du projet, et vous répond dans votre propre langue. Les contrôles de contradiction qu’il lance utilisent les règles de cette langue.

Ce qu’elle ne change jamais : rien de ce que vous avez saisi n’est traduit, et changer le réglage ne réécrit aucun texte existant. Réglez la langue avant d’écrire, ou réécrivez les textes vous-même.

## 16. Raccourcis clavier

Le tableau donne les raccourcis pour Windows et Linux. Sur un Mac, lisez ⌘ pour Ctrl, ⌥ pour Alt et ⇧ pour Shift ; les menus et les infobulles affichent la notation de votre système, et le panneau latéral se fait avec ⌃⌘1 (Contrôle et Commande). **Rechercher une commande…** (Ctrl+K) trouve toutes les commandes, et **Raccourcis clavier** (Ctrl+/) liste celles qui ont un raccourci. Les menus, la recherche de commande et cette fenêtre n’affichent que les raccourcis qui fonctionnent.

| Raccourci | Action |
|---|---|
| Ctrl+K | Rechercher une commande… |
| Ctrl+/ | Raccourcis clavier |
| Ctrl+, | Préférences… |
| Échap | Fermer, dans cet ordre : la recherche de commande, la fenêtre ouverte, le menu ouvert, un aperçu ou une comparaison de prises ; sinon désélectionner |
| Ctrl+Z, Ctrl+Shift+Z | Annuler, Rétablir |
| Ctrl+S | Enregistrer |
| Ctrl+O | Ouvrir… |
| Ctrl+I | Importer depuis la bibliothèque… |
| Ctrl+Alt+I | Importer depuis l’ordinateur… |
| Ctrl+E, Ctrl+Shift+E | Exporter la vidéo…, Exporter vers un autre logiciel… |
| Ctrl+G | Générer la sélection |
| Ctrl+Alt+G | File de génération |
| Ctrl+Shift+G | Passer la prise en final |
| Ctrl+J | Assistant PotionUI (ouvre le chat en mode Video Producer assistant) |
| Ctrl+Alt+1 | Panneau latéral |
| Espace | Lecture / pause |
| Ctrl+B | Couper à la tête de lecture |
| Ctrl+Shift+B, Ctrl+Alt+B | Découper le clip audio sélectionné en tranches de la durée réglée dans l’inspecteur, Recoller ses tranches |
| Ctrl+D | Dupliquer |
| Retour arrière, Suppr | Supprimer (une piste audio sélectionnée : la supprimer après confirmation) |
| A, R, B | Outil Sélection, Outil Plage, Outil Lame |
| I, O | Définir le point d’entrée, Définir le point de sortie |
| Alt+X | Effacer la plage |
| Alt+[, Alt+] | Ajuster le début à la tête, Ajuster la fin à la tête |
| M | Ajouter un marqueur |
| N | Magnétisme |
| F, U, Alt+Retour arrière | Favori, Retirer la marque, Rejeter |
| Flèche gauche, Flèche droite | Déplacer la tête de lecture d’une image, soit 1/fps du projet (1 s avec Shift) |
| Flèche gauche, Flèche droite (Storyboard) | Sélectionner le plan précédent ou suivant |
| Home, Fin | Aller au début, Aller à la fin |
| D | Synopsis et découpage (le panneau de gauche dans la grille) |
| T, E | Les prises du plan choisi (au moniteur dans la bande), Éditeur de plan |
| Flèche haut, Flèche bas (Storyboard) | Dans la bande : prise précédente ou suivante du plan au moniteur |
| Entrée (Storyboard) | Dans la bande, avec une prise au moniteur : utiliser la prise |
| <, > (Storyboard) | Dans la bande : raccourcir, allonger le plan choisi de 0,5 s |
| Ctrl+Shift+Flèche gauche, Ctrl+Shift+Flèche droite (Storyboard) | Avancer ou reculer le plan choisi d’une place |
| Shift+R (Storyboard) | Dans la bande : comparer le raccord avec le plan précédent |

Les raccourcis à une lettre (A, R, B, I, O, M, N, F, U, D, T et E) peuvent être désactivés dans **Video Producer › Préférences…**, réglage **Raccourcis à une touche**, activé par défaut. Espace, Retour arrière, Suppr, les flèches, Home et Fin n’en dépendent pas.

Quand les raccourcis fonctionnent :

- Seulement quand le focus est sur la page et pas dans un champ de texte. Avec un champ de texte actif, une fenêtre ouverte (sélecteur ou confirmation PotionUI compris) ou la recherche de commande ouverte, les autres raccourcis sont inactifs ; Échap, Ctrl+K et Ctrl+/ agissent toujours. Tant que le chat PotionUI est ouvert, les raccourcis de la page sont inactifs.
- Une combinaison n’agit qu’avec exactement ses touches. Ctrl+Shift+I et Ctrl+Shift+J (sur un Mac Option+Commande+I, J ou K) restent aux outils de développement du navigateur, et Alt+Flèche gauche continue de revenir en arrière. La page ne prend jamais les combinaisons qui gèrent les onglets et les fenêtres du navigateur (Ctrl+N, Ctrl+T, Ctrl+W, Ctrl+Tab, Ctrl+1 à Ctrl+9), sa barre d’adresse (Ctrl+L), sa recherche dans la page (Ctrl+F) ni le presse-papiers (Ctrl+C, Ctrl+V) : pour les espaces de travail, un nouveau projet ou un nouveau titre, utilisez le menu, les boutons ou le sélecteur d’espaces.
- Une touche maintenue enfoncée ne répète pas une commande qui bascule quelque chose (Espace, M, N, F, U, Ctrl+S, Ctrl+G, Ctrl+D et les autres). Annuler, Rétablir, Supprimer et les flèches se répètent.
- Sur un Mac, Ctrl+K dans un champ de texte reste à l’éditeur de texte ; la recherche de commande se fait avec ⌘K. Le / de Ctrl+/ demande Shift sur certaines dispositions de clavier, comme la disposition française : la page l’accepte dans les deux cas.

### Clavier et lecteurs d’écran

Chaque bouton a un nom accessible, et un bouton d’icône affiche son infobulle quand il reçoit le focus du clavier, pas seulement au survol de la souris. La touche Tab atteint chaque commande avec un anneau de focus visible, y compris le premier choix d’une fenêtre ouverte à la souris. Les poignées d’ajustement et de fondu de la timeline sont des poignées pour la souris que Tab ignore : utilisez le menu **Montage** et l’inspecteur à la place (chapitres 3 et 7). Un lecteur d’écran entend la progression d’une génération ou d’un export à chaque palier de 10 %, ou quand l’étape change, et jamais plus d’une fois toutes les 3 secondes.

## 17. Ce qui est simulé

Certaines parties gardent leur interface mais ne font pas la vraie chose. Elles portent un badge gris pointillé, **Simulé**, jamais jaune : le jaune est réservé aux vrais points à vérifier. **Aide › Fonctions simulées** ouvre la liste des cinq éléments ci-dessous. Ce que le moteur choisi ne sait pas faire n’est pas une simulation, et porte à la place un badge gris uni : un profil grisé (« Ref2VA : MiniMax H3 seulement »), **Agrandisseur indisponible** et **Non transmis à ce moteur** (chapitres 8 et 9).

Le badge **Simulé** apparaît dans l’en-tête de la fenêtre **Atelier Sound design** (intitulée **Voix et dialogues** pour une voix) ; à côté des formats **Fichier maître · ProRes 422** et **Archive · H.265** quand l’un d’eux est choisi, à côté des stems audio et, quand un format simulé est choisi, dans le pied de l’onglet **Vidéo** de la fenêtre d’export (« Rendu simulé : maître et archive ») ; sur le bouton d’automation des tranches de la console ; et sur la ligne d’identité de la vérification de l’assistant (chapitre 10).

Tout le reste fonctionne pour de vrai : la génération elle-même (les moteurs activés par votre admin, l’estimation, les prises avec leur progression, l’annulation et la reprise, les finals par agrandissement ou nouveau rendu, le quota et les notifications), les projets enregistrés, **Fichier › Ouvrir…**, **Fichier › Historique des versions…** et **Fichier › Nouveau projet…**, l’import de vos images, vidéos et fichiers audio avec leurs vignettes et leur lecture, le montage sur la timeline (ajustement des plans, fondus, coupe, magnétisme, plage, marqueurs, annuler et rétablir), la sélection et l’inspecteur, le Storyboard (le bouton **Proposer un découpage** est une simple coupe par phrases, pas une simulation), l’assistant PotionUI avec ses quatre outils (chapitre 10), la bibliothèque de prompts et le compositeur, le contrôle des contradictions de direction, le raccord de couleur, le recadrage depuis la 3D (scènes tirées d’une image, caméra et captures), la console de mixage qui joue vos fichiers audio, les images de raccord, les vidéos web et réseaux sociaux (des fichiers MP4 que ffmpeg assemble sur le serveur) et les fichiers FCPXML, OpenTimelineIO, EDL et SRT, qui sont de vrais fichiers.

La fenêtre **Fonctions simulées** liste cinq éléments. Pour chacun, le tableau donne ce que dit la fenêtre et ce qui est réel à côté.

| Élément de la fenêtre | Ce que dit la fenêtre | Ce qui est réel à côté |
|---|---|---|
| **Score d’identité** | La similarité d’identité entre deux plans, dans le contrôle des raccords et dans la revue de l’assistant, est simulée. Le raccord couleur, lui, analyse réellement les images. | Le contrôle de couleur analyse réellement les images : les images de raccord des plans et leurs vignettes (chapitre 12). Aucune mesure d’identité n’est offerte aux plugins, le pourcentage reste donc simulé. |
| **Synchronisation labiale** | Aucune synchronisation labiale n’est calculée : les options de synchronisation de l’atelier Sound design restent dans le projet et ne changent ni les prises ni l’export. | MiniMax H3 fait l’image et le son en une passe : il n’y a pas d’étape de synchronisation séparée. Le texte des dialogues alimente bien les sous-titres. |
| **Voix et dialogues générés** | L’atelier Sound design ne génère ni voix, ni dialogue, ni son : la préparation est simulée et ce que vous entendez est une synthèse simple dans le navigateur. Le texte des dialogues alimente les sous-titres, et les fichiers audio importés sont lus réellement. | Les fichiers audio que vous importez sont lus pour de vrai par la console (chapitre 13). PotionUI n’a aucun preset de parole ou de bruitage pour préparer les ambiances, bruitages, textures, impacts ou la musique de l’atelier. |
| **Automation et traitements de la console** | Le bouton Auto ne fait que changer de mode : aucune courbe d’automation n’est enregistrée. Le panoramique, les inserts, les envois et le bus master s’entendent dans le navigateur mais ne sont pas appliqués à la vidéo exportée, qui garde le gain, les faders de piste, mute, solo et les fondus. | La console joue vraiment vos fichiers audio : faders, muet et solo, panoramique, égaliseur, compresseur, filtre, envois et vumètres agissent sur le son que vous entendez. La vidéo exportée applique le gain, les faders de piste, muet, solo et les fondus (chapitre 14). |
| **ProRes, H.265 et stems** | Le fichier maître (ProRes), l’archive (H.265) et les stems audio sont simulés : aucun fichier n’est écrit. Les vidéos MP4 web et réseaux sociaux et les fichiers FCPXML, OTIO, EDL et SRT sont réels. | Les vidéos web et réseaux sociaux et les fichiers FCPXML, OpenTimelineIO, EDL et SRT sont réels (chapitre 14). Le convertisseur vidéo de PotionUI n’écrit que du H.264 MP4 ou du WebM VP9, et aucun audio n’est rendu par rôle. Pour les formats simulés, la fenêtre se termine par « Rendu simulé terminé : aucun fichier n’est écrit pour ce format. » |

L’**Atelier avancé** des versions précédentes a disparu, avec ses réglages que le moteur n’utilisait pas. Ce qui agissait est maintenant dans la section **Moteur** de Director IA (moteur, profil, qualité par défaut, brouillons) et dans l’éditeur de plan (moteur, profil, qualité et graine d’un plan). Les réglages retirés étaient : cohérence entre fenêtres, verrouillage de l’identité des personnages, priorité au guide de mouvement, les fenêtres de génération avec leur longueur et leur chevauchement, la résolution finale, la graine, les étapes, le guidage (CFG), les LoRAs, la piste qui guide la performance, la synchronisation labiale, le rythme du montage, le décalage audio / image, le nommage des résultats, les post-traitements, l’insertion automatique de la variante A, et les poids du Hybrid builder avec ses profils enregistrés. Un projet fait avant garde leurs valeurs, que rien ne lit ; un preset n’expose que les contrôles qu’il déclare ; MiniMax H3, par exemple, n’a ni guidage ni prompt négatif. La graine d’une prise est tirée par le serveur et affichée sur sa carte, sauf si le plan fixe la sienne, et les résolutions suivent les règles du brouillon et du final du chapitre 8.

L’assistant, lui, n’est pas simulé : c’est le chat PotionUI en mode Video Producer assistant, qui écrit les instructions de plan, corrige les contradictions avec la direction globale, découpe un synopsis en plans et vérifie la continuité, et vous approuvez chaque changement avant qu’il touche le projet (chapitre 10). Le seul point simulé de ce qu’il montre est la ressemblance d’identité entre deux prises.

## 18. Dépannage

- **La barre Production n’affiche aucun moteur.** Le menu indique « Aucun moteur ». Votre admin n’a pas terminé la mise en place : un moteur, un preset vidéo qui vous est attribué, ou un modèle vidéo activé chez le fournisseur cloud. Demandez-lui d’ouvrir Admin → Plugins → Video Producer.
- **L’estimation affiche « — » pour le temps.** Rien n’a encore été mesuré pour ce preset, ce moteur et cette résolution (la calibration est vide). Elle se remplit après quelques générations.
- **« Passera par la RAM de l’hôte, plus lent. »** L’estimation de mémoire dépasse celle du GPU. La génération n’est pas bloquée. Si le serveur manque de mémoire libre pour cela, le moteur refuse de démarrer et la prise échoue (`host_ram_oom`).
- **Le quota est épuisé.** **Générer la sélection** dit « Quota GPU dépassé » jusqu’au mois suivant ou jusqu’à ce que votre admin relève la limite de votre plan. Les générations en cours ne sont pas arrêtées, et une prise qui échoue ou qui est annulée rend ses minutes. Les premières prises d’un preset comptent 10 secondes de GPU par seconde de vidéo, ce qui peut paraître généreux tant que les durées réelles n’ont pas été mesurées.
- **Générer la sélection est désactivé.** Lisez le message de la barre : pas de plage, ni direction ni instruction locale, une instruction vide, aucun moteur, un preset qui n’est pas le vôtre, un profil que le moteur ne sait pas générer, des modèles à installer, un modèle cloud à choisir, ou le quota.
- **« Modèles à installer pour ce preset : … ».** Votre admin n’a pas téléchargé les fichiers de modèle dont ce preset a besoin. Demandez-les-lui.
- **Un avertissement dit que les plans seront générés à partir du texte seul.** Le profil FL2VA n’a aucune frame liée au plan. Ajoutez une frame de départ ou d’arrivée (**Utiliser la dernière image du plan précédent** prend la première dans le plan précédent, chapitre 12), ou choisissez un autre profil H3 ; la génération n’est pas bloquée.
- **Une prise reste En file.** Votre admin limite le nombre de générations que vous pouvez avoir en cours en même temps : la prise démarre d’elle-même quand l’une des vôtres se termine, dans l’ordre de la file. L’onglet **File** de Director IA montre sa place ; **Passer en tête de file** en fait la suivante. Si elle reste En file alors que rien de vous ne tourne, prévenez votre admin.
- **Une prise a échoué.** La carte explique les causes habituelles dans votre langue (par exemple « La mémoire du GPU du serveur est saturée : essayez une résolution plus basse ou moins de frames. ») ; pour toute autre cause elle affiche la raison que donne PotionUI (en anglais) ou, s’il n’en donne aucune, « La génération a échoué » suivi d’un code. **Réessayer** lance une nouvelle prise pour le même plan, avec la même graine. Causes fréquentes : le GPU a manqué de mémoire (`cuda_oom` : essayez un brouillon, un plan plus court ou un autre moteur) ; un fichier de modèle manque sur le serveur (`missing_model_file` : demandez à votre admin de le télécharger de nouveau) ; le serveur a manqué de mémoire en faisant passer le modèle par sa RAM (`host_ram_oom`). Si PotionUI a redémarré pendant la génération, la prise est marquée en échec et la génération ne peut pas reprendre : utilisez **Réessayer**. Si toutes les prises échouent ensuite en quelques secondes après une erreur de mémoire, prévenez votre admin : le serveur a peut-être besoin d’un redémarrage.
- **« Agrandisseur indisponible » dans Passer en final.** Aucun agrandisseur ne vous est attribué : SeedVR2 agrandit les prises de Wan, LTX, MiniMax H3 Fast et VDN, des presets (12 GB) et des modèles cloud. Utilisez **Générer à nouveau en pleine résolution**, ou interrogez votre admin sur SeedVR2.
- **Les références sont ignorées avec MiniMax H3.** Demandez à votre admin de vérifier le fichier de modèle choisi pour le mode Références. Le moteur ignore les références d’un profil autre que Ref2VA, et de tout autre preset.
- **J’ai fermé la page pendant une génération.** Les prises continuent ; rouvrez le projet pour les retrouver. Les notifications vous disent quand elles se terminent.
- **La fenêtre d’export dit « ffmpeg est absent du serveur : les exports web et réseaux sociaux en ont besoin. »** Le serveur ne trouve pas ffmpeg, donc les vidéos web et réseaux sociaux ne peuvent pas être fabriquées. Demandez à votre admin de l’installer ; une fois fait, rechargez la page. Les fichiers pour un autre logiciel et les sous-titres se téléchargent toujours.
- **« Aucun plan n’a encore de fichier vidéo à exporter. »** Aucun plan de votre projet enregistré n’a de fichier vidéo ou image que le serveur peut trouver : tous les plans sont encore « À générer », ou les médias ont été retirés de votre bibliothèque ou de votre galerie. Générez ou importez les plans, puis exportez de nouveau. Un seul plan sans fichier n’arrête pas l’export : il est noir et silencieux dans la vidéo.
- **« Un export de ce projet est déjà en cours. »** Un projet n’a qu’un export à la fois. Attendez-le, ou cliquez sur **Annuler** sur sa carte.
- **« Le dossier d’export est plein : supprimez d’anciens exports et réessayez. »** Vos exports ont consommé votre budget de taille. Supprimez-en dans **Exports précédents** (les copies de votre bibliothèque restent), ou demandez à votre admin un budget d’export plus grand.
- **Un export reste En file.** Le serveur fait un export à la fois, pour tout le monde, le vôtre attend donc son tour. S’il ne démarre jamais, prévenez votre admin.
- **« Conversion en MP4 » est longue.** Une longue séquence en 4K peut prendre de nombreuses minutes sur un petit serveur ; le pourcentage montre où elle en est. L’export n’échoue avec « La vidéo n’a pas pu être convertie. » que si ffmpeg n’avance plus pendant 5 minutes. Exportez en 1080p ou en 720p pour aller plus vite.
- **Un export est en Échec.** La carte dit ce qui a échoué et, en dessous, le message du serveur. « ffmpeg n’a pas pu assembler la vidéo. » peut venir d’un fichier que ffmpeg ne sait pas lire, ou d’un redémarrage de PotionUI pendant l’export (« The server stopped during the export. ») ; relancez-le, et s’il échoue encore donnez le message à votre admin. « La vidéo n’a pas pu être enregistrée dans votre bibliothèque. » signifie que votre stockage PotionUI est plein : libérez de la place et exportez de nouveau.
- **Un plan est noir ou silencieux dans la vidéo.** Le serveur n’a trouvé aucun fichier pour ce plan (un média retiré de votre bibliothèque ou de votre galerie), ou le fichier n’a pas de bande son, ou son son est coupé : le plan ou la piste V1 est muet, ou une piste audio est en solo sans V1 (chapitre 13). Le son du panoramique, de l’égaliseur, du compresseur, du filtre, des envois et de l’automation de la console n’est pas dans le fichier (chapitre 14).
- **Un fichier FCPXML, OpenTimelineIO ou EDL ne retrouve pas ses médias.** Les chemins du fichier sont des chemins sur le serveur PotionUI. Copiez les médias sur votre ordinateur de montage et reliez-les de nouveau dans votre logiciel (chapitre 14).
- **« Cet export n’existe plus. » ou « La vidéo n’est pas encore prête. »** au téléchargement : l’export a été supprimé, ou il est encore en cours. Exportez de nouveau, ou attendez la fin sur la carte.
- **Une image de raccord est refusée.** « Ce plan n’a pas de plan précédent. » (le premier plan ne peut pas en prendre) ; « “Plan 1” n’a encore ni prise ni vidéo. » ou « Le plan précédent n’a ni prise ni vidéo dont reprendre une image. » (générez et choisissez d’abord une prise pour le plan précédent) ; « ffmpeg manque sur le serveur : la dernière image ne peut pas être reprise. » (prévenez votre admin) ; « L’image n’a pas pu être extraite de la prise. » ou « L’image n’a pas pu être extraite : réessayez. » (réessayez, et prévenez votre admin si cela persiste) ; « Le projet n’a pas pu être enregistré : aucune image extraite. » (le projet doit d’abord être enregistré : voyez l’état d’enregistrement dans la barre projet).
- **La barre projet indique « Non enregistré — réessayer ».** Le dernier enregistrement a échoué : la connexion a été coupée, ou le serveur a refusé le projet. Un message dit lequel. Cliquez sur l’état d’enregistrement ou sur le bouton **Réessayer** du message pour réessayer. Vos modifications restent dans la page et la modification suivante réessaie aussi. Tant qu’un enregistrement ne passe pas, ouvrir un autre projet ou restaurer une version demande de confirmer avant d’abandonner ces modifications. Si le message dit que le contenu a été refusé ou que le projet est trop volumineux, voyez votre admin : recharger la page ferait perdre les modifications non enregistrées.
- **« Projet rechargé : il a été modifié ailleurs ».** Le projet a été enregistré depuis un autre onglet, une autre fenêtre ou un autre appareil après son ouverture chez vous, alors la page a chargé la version enregistrée. Les modifications que vous n’aviez pas enregistrées dans cette page sont perdues. Travaillez sur un projet à un seul endroit à la fois ; **Fichier › Historique des versions…** ramène un état antérieur.
- **« Ce projet a été supprimé ailleurs ».** Le projet a été supprimé depuis un autre onglet ou un autre appareil pendant qu’il était ouvert ici. La page a ouvert votre projet modifié le plus récemment, ou créé le projet de départ. Les modifications que vous n’aviez pas enregistrées sont perdues.
- **Un média ne s’affiche pas ou ne se lit pas.** Le visualiseur affiche **Média hors ligne** (« Le fichier source de “…” n’est plus disponible : importez-le à nouveau ou choisissez une prise. ») et la vignette du plan sur la timeline aussi : le fichier n’est plus disponible dans votre bibliothèque ou votre galerie PotionUI. Importez-le à nouveau, ou choisissez une prise pour le plan. Une prise dont vous avez supprimé la génération de la galerie ne se lit plus non plus.
- **« 1 fichier n’a pas pu être importé » (ou « N fichiers n’ont pas pu être importés »).** Le fichier n’est plus disponible dans la bibliothèque ou la galerie, ou son type n’est pas accepté par la fenêtre : images et vidéos pour **Importer depuis la bibliothèque…** et **Depuis la galerie PotionUI**, audio pour **Importer un son de la bibliothèque…**.
- **« « … » n’a pas pu être importé : … ».** Un fichier de l’ordinateur n’a pas atteint votre bibliothèque. La raison suit : le fichier est trop volumineux pour le serveur, la connexion a été perdue, ou PotionUI l’a refusé (son message s’affiche, par exemple quand votre plan de stockage est plein). Libérez de la place dans votre bibliothèque ou demandez à votre admin, puis importez le fichier de nouveau.
- **La vue 3D indique que le navigateur ne peut pas afficher la 3D.** La page demande WebGL 2. Activez l’accélération matérielle de votre navigateur, ou utilisez un Chrome, un Edge, un Firefox ou un Safari récent.
- **Une scène tirée d’une image a échoué.** La vue de Recadrer depuis la 3D donne la raison : vos minutes GPU sont épuisées, le preset Image to Splat ne vous est pas disponible (demandez à votre admin), ou l’image n’a pas pu être lue ou extraite de la vidéo. Cliquez sur **Réessayer** ; si l’échec se répète, prévenez votre admin.
- **Des trous apparaissent dans une capture, ou la caméra ne bouge plus.** Une image ne montre qu’un côté des choses : quand la caméra approche du bord de la zone fiable (« Trous probables »), des zones vides apparaissent derrière les objets, et la caméra s’arrête sur ce bord, à 15° ou 25 % de la vue d’origine. Revenez vers la **Vue d’origine**, ou construisez une scène à partir d’une image prise plus près de l’angle voulu (chapitre 4, Recadrer depuis la 3D).
- **L’assistant ne répond pas, n’affiche aucune carte ou agit sur le mauvais projet.** Voyez le chapitre 10, « Si cela ne fonctionne pas ».


## 19. Glossaire

| Français | English | Sens |
|---|---|---|
| plan | shot | Un morceau du film, une génération. |
| prise | take | Une version générée d’un plan : une vraie vidéo produite par le moteur choisi. |
| brouillon | draft | Une prise rapide, en résolution réduite, pour juger le mouvement et le cadrage. |
| final | final | La prise retenue, agrandie (agrandissement) ou générée à nouveau à la plus grande résolution (nouveau rendu). |
| étiquette | label | Brouillon, Candidate, Rejetée ou Finale : le tri que vous avez fait d’une prise. La prise Finale est celle que le plan joue (chapitre 9). |
| brouillons par plan | drafts per shot | Combien de prises les boutons Générer d’un plan font d’un coup, de 1 à 8 ; le nombre du projet quand le plan n’en a pas (chapitre 8). |
| éditeur de plan | shot editor | La fenêtre qui réunit l’instruction, la durée, les images clés, les références, les brouillons et le moteur d’un plan (chapitre 4). |
| moteur propre | own engine | Le moteur, le profil, la qualité ou la graine qu’un plan fixe lui-même dans son éditeur de plan, à la place de ceux du projet (chapitre 4). |
| référence sonore | sound reference | Une voix, une musique ou une ambiance de la famille de références **Son**, envoyée avec la génération d’un plan (chapitre 13). |
| piste de référence | reference track | Une piste audio cochée **Référence pour la génération** : sa portion sous chaque plan accompagne la génération, sauf les clips désactivés un à un (chapitre 13). |
| mixé sur la prise | mixed onto the take | Posé sur la prise terminée comme bande-son, sans guider l’image : ce que LTX fait du son d’un plan (chapitre 13). |
| file de génération | generation queue | Vos prises qui attendent le moteur ou sont en cours, dans l’ordre où elles passent, partagées par tous vos projets ; l’onglet **File** de Director IA (chapitre 8). |
| Prompt modifié | Prompt modified | La marque d’une prise faite avant la dernière modification de son plan (chapitre 4). |
| moteur | engine | Ce qui produit les prises : un preset vidéo sur le matériel de votre admin, ou un modèle cloud. |
| variante | variant | Une des prises (A, B, …) faites pour un même plan en une génération. |
| graine | seed | Le nombre qui fixe le hasard d’une prise ; la même graine donne une prise semblable. |
| calibration | calibration | Les durées réelles de vos générations passées, gardées par preset, moteur et résolution, que l’estimation utilise pour son temps ; elle affiche « — » tant qu’il n’y en a pas. |
| raccord | match | Faire se ressembler deux plans voisins (couleur) ou garder la même identité. |
| image de raccord | seam frame | Une image tirée d’une prise et utilisée comme première ou dernière image d’un plan, le plus souvent la dernière image du plan précédent, pour qu’un plan démarre là où le précédent s’est terminé (chapitre 12). |
| fondu | fade | Un début ou une fin progressive d’un clip. |
| tête de lecture | playhead | La position courante sur la timeline. |
| plage | range | Une partie de la timeline entre un point d’entrée et un point de sortie. |
| direction globale | global direction | Le texte qui guide toutes les générations. |
| langue des prompts | prompt language | La langue de la direction globale et des instructions locales d’un projet, anglais ou français. |
| version | version | Un état enregistré du projet ; **Historique des versions…** les liste et en restaure une. |
| instruction locale | shot prompt | Le texte d’un plan ; il complète la direction globale. |
| guide de mouvement | motion guide | Une vidéo de la famille de références **Guides de mouvement** : avec le profil Ref2VA, MiniMax H3 reprend son mouvement dans le plan (chapitre 8). |
| Control video | Control video | Le type du guide de mouvement qu’un projet fait avec une version antérieure reçoit de la vidéo de référence de chaque plan 3D (chapitre 4). |
| Gaussian Splat | Gaussian Splat | Une scène 3D faite de nombreuses petites taches colorées, tirée d’une image, dans laquelle une caméra peut se déplacer (chapitre 4, Recadrer depuis la 3D). |
| recadrage | reframing | Filmer une image sous un autre angle dans **Recadrer depuis la 3D**, pour la première ou la dernière image d’un plan (chapitre 4). |
| vue d’origine | source view | La caméra de l’image d’où vient une scène : la scène est juste autour d’elle. |
| zone fiable | reliable zone | La partie d’une scène autour de la vue d’origine où la caméra peut aller : 15° autour d’elle, 25 % de sa distance, aucune focale plus large que celle de l’image (chapitre 4). |
| profil H3 | H3 profile | FL2VA, Ref2VA ou Hybrid AV : ce qui guide la génération. |
| mode | mode | Une façon de travailler du chat PotionUI, avec ses propres instructions et outils. Cette page utilise **Video Producer assistant** ; une conversation garde son mode. |
| outil | tool | Une action que l’assistant peut lancer dans votre projet : écrire une instruction de plan, corriger les contradictions, découper le synopsis, vérifier la continuité. |
| approbation | approval | La carte où vous acceptez (**Approve**) ou refusez (**Reject**) ce que l’assistant propose. Rien ne change avant votre approbation. |
| contexte | context | Le résumé de votre projet que la page envoie à l’assistant avec chaque message (chapitre 10). |
| job d’export | export job | Un export vidéo en attente ou en cours sur le serveur, avec son état et sa progression. Une fois terminé, il reste dans **Exports précédents** (chapitre 14). |
| mezzanine | mezzanine | La vidéo intermédiaire de haute qualité que le serveur assemble d’abord, puis convertit en MP4 à télécharger. Vous ne la manipulez jamais (chapitre 14). |
