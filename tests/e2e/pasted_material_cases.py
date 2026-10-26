"""
A case set of PASTED MATERIAL: real text that carries other people's positions
and none of the reader's. Built by `screen_pasted_material.py` on 2026-10-26;
read that module for the sourcing, the licences and the blind screen.

REPORTAGE items are Wikinews articles (CC BY 2.5, attribution by URL).
DIALOGUE items are windows of Hansard Commons contributions (Open Parliament
Licence, attribution by debate URL); speakers are named members speaking in
public session. `positions` is the blind screen's own list of the positions the
text carries, each with its holder — what the probe's reads choose among. `text`
is the ONLY field a writer under test may see.
"""

from __future__ import annotations

from typing import NamedTuple


class PastedMaterialCase(NamedTuple):
    case_id: str
    kind: str  # "reportage" | "dialogue"
    source: str  # title or debate name
    url: str
    text: str
    positions: tuple[tuple[str, str], ...]  # (holder, position)


PASTED_MATERIAL_CASES: tuple[PastedMaterialCase, ...] = (
    PastedMaterialCase(
        case_id="rep-83aa9ed1",
        kind="reportage",
        source=(
            "2008 US beef protest in South Korea"
        ),
        url=(
            "https://en.wikipedia.org/?curid=17743774"
        ),
        text=(
            "The 2008 US beef protest in South Korea was a series of protest demonstrations made "
            "between 24 May 2008 and mid August 2008. against president Lee Myung-bak in Seoul, "
            "Korea. The protest involved several hundred thousand and at its height up to one "
            "million people. The protest began after the South Korean government reversed a ban "
            "on US beef imports. The ban had been in place since December 2003, when mad cow "
            "disease was detected in US beef cattle. The protests occurred on a background of "
            "talks concerning the US-Korea free trade agreement. Critics accused the move as an "
            "attempt by the Korean government to please the US government. Local media also "
            "criticized the government's attempt. An example of this is the Munhwa Broadcasting "
            "Corporation (MBC) PD Note program \"Is American Beef Really Safe from Mad Cow "
            "Disease? (긴급취재, 미국산 쇠고기, 과연 광우병에서 안전한가)\" televised on 27 April 2008. Lee Myung-bak's "
            "popularity plummeted after the decision and protests."
        ),
        positions=(
            (
                "Protesters",
                "The government should not have reversed the ban on US beef imports, because of mad "
                "cow disease concerns.",
            ),
            (
                "South Korean government (President Lee Myung-bak)",
                "The ban on US beef imports should be reversed.",
            ),
            (
                "Critics",
                "The reversal was an attempt by the Korean government to please the US government.",
            ),
            (
                "Local media (e.g., MBC's PD Note program)",
                "The government's attempt to resume US beef imports is open to criticism, questioning "
                "whether American beef is safe from mad cow disease.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-b8d03a32",
        kind="reportage",
        source=(
            "2022 National Taiwan University dormitory counselor sexual harassment case"
        ),
        url=(
            "https://en.wikipedia.org/?curid=83516260"
        ),
        text=(
            "In 2022, a dormitory counselor at National Taiwan University (NTU) was accused of "
            "sexually harassing a resident student. During the handling of the case, NTU's Gender "
            "Equity Education Committee concluded that sexual harassment had not occurred. "
            "However, the Taipei High Administrative Court later ruled that the committee had "
            "been improperly constituted and revoked its decision. The Control Yuan censured NTU "
            "over numerous deficiencies in its handling of the case, while the Ministry of "
            "Education repeatedly ordered the university to reopen the investigation. Additional "
            "controversies arose over the disclosure of the victim's personal information. In "
            "March 2026, the dormitory counselor was sentenced to seven months' imprisonment for "
            "violating the Stalking and Harassment Prevention Act."
        ),
        positions=(
            (
                "NTU's Gender Equity Education Committee",
                "Sexual harassment had not occurred in the dormitory counselor case.",
            ),
            (
                "Taipei High Administrative Court",
                "The committee had been improperly constituted, so its decision was revoked.",
            ),
            (
                "Control Yuan",
                "NTU had numerous deficiencies in its handling of the case and deserved censure.",
            ),
            (
                "Ministry of Education",
                "NTU should reopen the investigation.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-dd74b405",
        kind="reportage",
        source=(
            "Attorney General of Virginia's climate science investigation"
        ),
        url=(
            "https://en.wikipedia.org/?curid=28186231"
        ),
        text=(
            "The Attorney General of Virginia's climate science investigation was a civil "
            "investigative demand initiated in April 2010 by Virginia Attorney General Ken "
            "Cuccinelli, who rejects the scientific consensus on climate change, for a wide range "
            "of records held by the University of Virginia related to five grant applications for "
            "research work by a leading climate scientist Michael E. Mann, who was an assistant "
            "professor at the university from 1999 to 2005. The demand was issued under the "
            "Virginia Fraud Against Taxpayers Act in connection with claims by Cuccinnelli that "
            "Mann had possibly violated state fraud laws in relation to five research grants, by "
            "allegedly manipulating data. No evidence of wrongdoing was presented to support the "
            "claim. Mann's earlier work had been targeted by climate change deniers attacking the "
            "hockey stick graph, and allegations against him were renewed in late 2009 in the "
            "Climatic Research Unit email controversy but found to be groundless in a series of "
            "investigations. Widespread concerns were raised by University of Virginia's faculty "
            "and numerous scientists and science organizations that Cuccinelli's actions posed a "
            "threat to academic freedom, and would have a chilling effect on research in the "
            "state. The university filed a court petition and the judge dismissed Cuccinelli's "
            "demand on the grounds that no justification had been shown for the investigation. "
            "Cuccinelli tried to re-open his case by issuing a revised subpoena, and appealed the "
            "case to the Virginia Supreme Court. The case was defended by the university, and the "
            "court ruled that Cuccinelli did not have the authority to make these demands. The "
            "outcome was seen as a victory for academic freedom."
        ),
        positions=(
            (
                "Ken Cuccinelli (Virginia Attorney General)",
                "Michael Mann possibly violated state fraud laws by manipulating data in relation to "
                "five research grants, justifying a civil investigative demand on the University of "
                "Virginia.",
            ),
            (
                "Michael E. Mann and the University of Virginia",
                "The demand was unjustified and should be resisted; the university defended the case "
                "and petitioned the court against it.",
            ),
            (
                "University of Virginia faculty, numerous scientists and science organizations",
                "Cuccinelli's actions threatened academic freedom and would chill research in the "
                "state.",
            ),
            (
                "The courts (the judge and the Virginia Supreme Court)",
                "No justification had been shown for the investigation, and Cuccinelli lacked the "
                "authority to make these demands.",
            ),
            (
                "Climate change deniers",
                "Mann's work, including the hockey stick graph, was open to attack, and allegations "
                "against him were renewed in 2009.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-d594b46f",
        kind="reportage",
        source=(
            "Beyond Citizen Kane"
        ),
        url=(
            "https://en.wikipedia.org/?curid=1563389"
        ),
        text=(
            "Beyond Citizen Kane is a 1993 British documentary film directed by Simon Hartog, "
            "produced by John Ellis, and first broadcast on Channel 4. It details the dominant "
            "position of the Globo media group, the largest in Brazil, and discusses the group's "
            "influence, power, and political connections. Globo's president and founder Roberto "
            "Marinho was criticised and compared to the fictional newspaper tycoon Charles Foster "
            "Kane, created by Orson Welles for the 1941 film Citizen Kane. According to the "
            "documentary, Marinho's media group engages in manipulation of news to influence "
            "public opinion. TV Globo (known as Rede Globo at the time of filming) objected to "
            "the film's position and tried to buy Brazilian rights, but Hartog had already made "
            "agreements to give non-television rights to political and cultural groups in Brazil. "
            "However, the documentary cannot be broadcast on television in Brazil since it "
            "contains large sections of footage owned by Globo. Nevertheless, copies sold in "
            "Britain reached Brazil in the 1990s and circulated widely there. In addition, since "
            "the internet boom of the early 21st century, the film has been released on "
            "video-sharing websites such as YouTube and Google Video."
        ),
        positions=(
            (
                "The documentary Beyond Citizen Kane (as the text reports it)",
                "Marinho's Globo media group manipulates news to influence public opinion.",
            ),
            (
                "Critics of Roberto Marinho",
                "Marinho resembles the fictional newspaper tycoon Charles Foster Kane.",
            ),
            (
                "TV Globo",
                "It objected to the film's position and sought to buy the Brazilian rights.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-49beb4d0",
        kind="reportage",
        source=(
            "Christmas controversies"
        ),
        url=(
            "https://en.wikipedia.org/?curid=3277499"
        ),
        text=(
            "Christmas is the Christian celebration of the birth of Jesus Christ, which, in "
            "Western Christian churches, is held annually on 25 December. For centuries, it has "
            "been the subject of several reformations, both religious and secular. In the 17th "
            "century, the Puritans had laws forbidding the ecclesiastical celebration of "
            "Christmas, unlike the Catholic Church or the Anglican Church, from the latter of "
            "which they separated. With the atheistic Cult of Reason in power during the era of "
            "the French Revolution, Christian Christmas religious services were banned and the "
            "three kings cake was forcibly renamed the \"equality cake\" under anticlerical "
            "government policies. Later, in the 20th century, Christmas celebrations were "
            "prohibited under the doctrine of state atheism in the Soviet Union. In Nazi Germany, "
            "Christmas celebrations were propagandized so as to serve the ideology of the Nazi "
            "party. Modern-day controversy, colloquially known as the \"war on Christmas\", occurs "
            "mainly in China, the United States and—to a much lesser extent—the United Kingdom. "
            "Some opponents have denounced the generic term \"holidays\" and avoidance of using the "
            "term \"Christmas\" as being politically correct. This often involves objections to "
            "government or corporate efforts to acknowledge Christmas in a way that is "
            "multiculturally sensitive. In China, the government not only does not recognize "
            "Christmas as a statutory holiday, but local governments restrict Christmas "
            "celebrations in some places."
        ),
        positions=(
            (
                "The Puritans (17th century)",
                "The ecclesiastical celebration of Christmas should be forbidden by law.",
            ),
            (
                "The French Revolution-era government (Cult of Reason)",
                "Christian Christmas services should be banned and the three kings cake renamed the "
                "'equality cake' under anticlerical policy.",
            ),
            (
                "The Soviet Union",
                "Christmas celebrations should be prohibited under the doctrine of state atheism.",
            ),
            (
                "Nazi Germany / the Nazi party",
                "Christmas celebrations should be propagandized to serve the party's ideology.",
            ),
            (
                "Some opponents in the modern 'war on Christmas' controversy",
                "The generic term 'holidays' and avoidance of 'Christmas' is politically correct and "
                "objectionable, as are government or corporate efforts to acknowledge Christmas in a "
                "multiculturally sensitive way.",
            ),
            (
                "The Chinese government and some local governments",
                "Christmas is not a statutory holiday and its celebration should be restricted in "
                "some places.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-1e650dc1",
        kind="reportage",
        source=(
            "Controversies surrounding Robert Falcon Scott"
        ),
        url=(
            "https://en.wikipedia.org/?curid=22479402"
        ),
        text=(
            "The British Antarctic explorer Robert Falcon Scott became the subject of controversy "
            "when, more than 60 years after his death on the return march from the South Pole in "
            "1912, his character came under sustained attack. Up to then Scott's image, in "
            "Britain and much of the world, had been that of heroic endeavour, the cornerstone of "
            "his reputation was his \"Message to the Public\" written just before his death. "
            "However, Roland Huntford's 1979 joint biography of Scott and his rival Roald "
            "Amundsen presented a contrasting view of Scott, not as hero but as bungler. The book "
            "was reissued in the 1980s as The Last Place on Earth, and was the subject of a 1985 "
            "television serial The Last Place on Earth. Although Huntford's objectivity was "
            "questioned, the book and related television drama changed the public's perception, "
            "with the \"bungler\" tag quickly becoming the new orthodoxy. In the 1980s and 1990s "
            "Scott was depicted negatively in several books. As Scott's reputation declined, that "
            "of his contemporary Ernest Shackleton, long overshadowed by Scott, was in the "
            "ascendent. Shackleton's man-management skills were celebrated, particularly in the "
            "United States, as models for business leaders. The first decade of the 21st century "
            "saw specific attempts to rescue Scott's reputation. Analysis of March 1912 "
            "meteorological data has been used to suggest Scott and his party might have been "
            "primarily the victims of unusually severe Antarctic weather, rather than "
            "incompetence. A 2003 Scott biography by polar explorer Sir Ranulph Fiennes included "
            "a defence of Scott, and was the first book to mount a serious attack on Huntford's "
            "thesis and credentials. Other biographical and historical works, television "
            "programmes and articles have continued to appear, representing different areas of "
            "the controversy's spectrum. In 2012, Karen May at the Scott Polar Research Institute "
            "re-discovered the fact that Scott had left written orders at Cape Evans to secure "
            "Scott's speedy return from the pole using dogs. This order was ultimately not "
            "carried out."
        ),
        positions=(
            (
                "Scott's reputation up to the 1970s (Britain and much of the world)",
                "Scott was a hero of heroic endeavour, a reputation grounded in his 'Message to the "
                "Public'.",
            ),
            (
                "Roland Huntford",
                "Scott was a bungler, not a hero.",
            ),
            (
                "Public opinion after Huntford's book and the television serial",
                "The 'bungler' tag became the new orthodoxy.",
            ),
            (
                "Critics of Huntford",
                "Huntford's objectivity is open to question.",
            ),
            (
                "Analysts of March 1912 meteorological data",
                "Scott and his party may have been primarily victims of unusually severe Antarctic "
                "weather rather than incompetence.",
            ),
            (
                "Sir Ranulph Fiennes",
                "Scott deserves a defence, and Huntford's thesis and credentials merit serious "
                "attack.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-46c80b66",
        kind="reportage",
        source=(
            "Downing Street memo"
        ),
        url=(
            "https://en.wikipedia.org/?curid=1893624"
        ),
        text=(
            "The Downing Street memo (or the Downing Street Minutes), sometimes described by "
            "critics of the Iraq War as the smoking gun memo, is the note of a 23 July 2002 "
            "secret meeting of senior British government, defence and intelligence figures "
            "discussing the build-up to the war, which included direct reference to classified "
            "United States policy of the time. The name refers to 10 Downing Street, the "
            "residence of the British prime minister. The memo, written by Downing Street foreign "
            "policy aide Matthew Rycroft, recorded the head of the Secret Intelligence Service "
            "(MI6) as expressing the view following his recent visit to Washington that \"[George "
            "W.] Bush wanted to remove Saddam Hussein, through military action, justified by the "
            "conjunction of terrorism and WMD. But the intelligence and facts were being fixed "
            "around the policy.\" It quoted Foreign Secretary Jack Straw as saying it was clear "
            "that Bush had \"made up his mind\" to take military action but that \"the case was "
            "thin.\" Straw also noted that Iraq retained \"WMD capability\" and that \"Saddam would "
            "continue to play hard-ball with the UN.\" The military asked about the consequences "
            "\"if Saddam used WMD on day one,\" posing Kuwait or Israel as potential targets. "
            "Attorney-General Lord Goldsmith warned that justifying the invasion on legal grounds "
            "would be difficult. However, the meeting took place several months before the "
            "adoption of United Nations Security Council Resolution 1441, the resolution "
            "eventually used as the legal basis for the invasion of Iraq. UNR687 also provided a "
            "pre-existing basis, as it required Iraq to divest itself of \"100%\" of all WMD "
            "capacity, which the Memo agreed it had not. A copy of the memo was obtained by "
            "British journalist Michael Smith and published in The Sunday Times in May 2005, on "
            "the eve of British elections. Smith stated that the memo was equivalent to the "
            "Pentagon Papers which exposed American intentions in the Vietnam War and alleged the "
            "American media did not report more about it due to a perceived bias towards support "
            "for the war. Though its authenticity has never been seriously challenged, the "
            "British and American governments have stated that the contents do not accurately "
            "reflect their official policy positions at the time."
        ),
        positions=(
            (
                "Head of MI6 (as recorded in the memo)",
                "Bush wanted to remove Saddam Hussein through military action justified by terrorism "
                "and WMD, and the intelligence and facts were being fixed around the policy.",
            ),
            (
                "Foreign Secretary Jack Straw (as recorded in the memo)",
                "Bush had made up his mind to take military action, but the case was thin; Iraq "
                "retained WMD capability and Saddam would keep playing hard-ball with the UN.",
            ),
            (
                "Attorney-General Lord Goldsmith (as recorded in the memo)",
                "Justifying the invasion on legal grounds would be difficult.",
            ),
            (
                "Critics of the Iraq War",
                "The memo is the 'smoking gun' showing the road to war was set in advance.",
            ),
            (
                "Michael Smith",
                "The memo is equivalent to the Pentagon Papers, and the American media under-reported "
                "it because of a perceived bias towards supporting the war.",
            ),
            (
                "British and American governments",
                "The memo's contents do not accurately reflect their official policy positions at the "
                "time.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-d610063a",
        kind="reportage",
        source=(
            "Esing Bakery incident"
        ),
        url=(
            "https://en.wikipedia.org/?curid=61267718"
        ),
        text=(
            "The Esing Bakery incident, also known as the Ah Lum affair, was a food contamination "
            "scandal in the early history of British Hong Kong. On 15 January 1857, during the "
            "Second Opium War, several hundred European residents were poisoned non-lethally by "
            "arsenic, found in bread produced by a Chinese-owned store, the Esing Bakery. The "
            "proprietor of the bakery, Cheong Ah-lum, was accused of plotting the poisoning but "
            "was acquitted in a trial by jury. Nonetheless, Cheong was successfully sued for "
            "damages and was banished from the colony. The true responsibility for the incident "
            "and its intention—whether it was an individual act of terrorism, commercial "
            "sabotage, a war crime orchestrated by the Qing government, or purely "
            "accidental—remain matters of debate. In Britain, the incident became a political "
            "issue during the 1857 general election, helping to mobilise support for the war and "
            "the incumbent prime minister, Lord Palmerston. In Hong Kong, it sowed panic and "
            "insecurity among the local colonists, highlighting the precariousness of imperial "
            "rule in the colony. The incident contributed to growing tensions between Hong Kong's "
            "European and Chinese residents, as well as within the European community itself. The "
            "scale and potential consequences of the poisoning make it an unprecedented event in "
            "the history of the British Empire, the colonists believing at the time that its "
            "success could have wiped out their community."
        ),
        positions=(
            (
                "the jury",
                "Cheong Ah-lum was not guilty of plotting the poisoning.",
            ),
            (
                "the court in the damages suit",
                "Cheong was liable for damages and was banished from the colony.",
            ),
            (
                "the text's account of the ongoing debate",
                "Responsibility and intention remain unsettled: an individual act of terrorism, "
                "commercial sabotage, a Qing-orchestrated war crime, or an accident.",
            ),
            (
                "the colonists at the time",
                "The poisoning, had it succeeded, could have wiped out their community.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-5ad4de7e",
        kind="reportage",
        source=(
            "Fred Thompson: Iraq had WMD in 2003"
        ),
        url=(
            "https://en.wikinews.org/wiki/Fred_Thompson%3A_Iraq_had_WMD_in_2003"
        ),
        text=(
            "Tuesday, October 2, 2007 In October United States Presidential candidate for 2008 "
            "Fred Thompson said about Iraq , \"We can't forget the fact that although at a "
            "particular point in time we never found any WMD down there he clearly had had WMD .\" "
            "However, the several different investigations, including the Iraq Survey Group "
            "headed by Charles Duelfer concluded, in part, that \"The ISG has not found evidence "
            "that Saddam possessed WMD stocks in 2003...\" Shortly after in October 2004 President "
            "George W. Bush said, \"Charles Duelfer has now issued a comprehensive report that "
            "confirms the earlier conclusion of David Kay that Iraq did not have the weapons that "
            "our intelligence believed were there.\" Share this article This page is archived , "
            "and is no longer publicly editable. Got a correction? Add the template {{ "
            "editprotected }} to the talk page along with your corrections, and it will be "
            "brought to the attention of the administrators . Please note that due to our "
            "archival policy , we will not alter or update the content of articles that are "
            "archived, but will only accept requests to make grammatical and formatting "
            "corrections. Note that some listed sources or external links may no longer be "
            "available online due to age. The text of this article is licensed under the terms of "
            "the Creative Commons Attribution 2.5 License Got a correction? Add the template {{ "
            "editprotected }} to the talk page along with your corrections, and it will be "
            "brought to the attention of the administrators . Please note that due to our "
            "archival policy , we will not alter or update the content of articles that are "
            "archived, but will only accept requests to make grammatical and formatting "
            "corrections. Note that some listed sources or external links may no longer be "
            "available online due to age."
        ),
        positions=(
            (
                "Fred Thompson",
                "Although no WMD were ever found, Saddam clearly had had WMD.",
            ),
            (
                "The Iraq Survey Group (headed by Charles Duelfer) and other investigations",
                "No evidence was found that Saddam possessed WMD stocks in 2003.",
            ),
            (
                "President George W. Bush",
                "The Duelfer report confirms David Kay's earlier conclusion that Iraq did not have "
                "the weapons intelligence believed were there.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-9e5cfc69",
        kind="reportage",
        source=(
            "Gorilla Project"
        ),
        url=(
            "https://en.wikipedia.org/?curid=11794476"
        ),
        text=(
            "The Gorilla Project refers to a former plan for construction of the first major oil "
            "refinery in the United States in over 30 years. In 2008, Hyperion Resources Inc., a "
            "Dallas-based energy company, had considered placing the 2,000-acre (810 ha), "
            "400,000-barrel-per-day (64,000 m3/d) capacity refinery near Elk Point, South Dakota "
            "and approximately 10 miles (16 km) away from Vermillion, among three other potential "
            "locations. Construction was originally intended to begin in 2008, but was "
            "progressively delayed. The state construction permit expired on March 15, 2013. The "
            "facility, which would process 400,000 barrels (64,000 m3) of oil a day and use 12 "
            "million US gallons (45,000 m3) of water daily from the Missouri River, caused "
            "significant controversy among concerned residents of Elk Point and the surrounding "
            "area. Prior to the announcement, the project and the company behind it were kept "
            "under considerable secrecy. It was known only as \"Project Gorilla\" while real estate "
            "agents made several purchase agreements on land north and east of Elk Point. Jeff "
            "Martin, a newspaper editor at the Argus Leader in Sioux Falls, uncovered two domain "
            "names, hyperionelkpoint.com and hyperionsd.com, which led to a news story that "
            "identified Hyperion for the first time. Elk Point is the forerunner among three "
            "other out-of-state locations Hyperion is considering for the refinery. Opponents are "
            "concerned about air, water, and noise pollution; environmental degradation of nearby "
            "food crops such as soy beans, corn, and alfalfa; negative effects on the ethanol "
            "fuel market and competition with local ethanol-producing farmers; the displacement "
            "of thousands of local residents and negative population resettling; potential "
            "industrial disasters including explosions, leaks, and spills, reminiscent of the "
            "recent explosion at a similar-capacity Texas City Oil Refinery that caused the "
            "deaths of 15 workers and injured over 100; contamination and overuse of important "
            "water resources from the Missouri River; potential threats of terrorism; and "
            "concerns of the sheer size of the facility, which will be over twice the area of Elk "
            "Point. In 2012 Hyperion allowed its development options on 5,000 acres of land in "
            "Union County to expire. Infrastructure to supply the refinery did not exist, "
            "financing had become difficult, demand had fallen, and with the delay of the "
            "Keystone XL pipeline, the feedstock to the proposed refinery would not have been "
            "available."
        ),
        positions=(
            (
                "Hyperion Resources Inc.",
                "A 400,000-barrel-per-day oil refinery should be built near Elk Point, South Dakota, "
                "as the leading candidate among its potential sites.",
            ),
            (
                "Opponents (concerned residents of Elk Point and the surrounding area)",
                "The refinery should not be built because of pollution, harm to crops and the ethanol "
                "market, resident displacement, industrial disaster and terrorism risks, Missouri "
                "River water use, and the facility's sheer size.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-22f75a34",
        kind="reportage",
        source=(
            "Growth in a Time of Debt"
        ),
        url=(
            "https://en.wikipedia.org/?curid=39156192"
        ),
        text=(
            "\"Growth in a Time of Debt\", also known by its authors' names as Reinhart–Rogoff, is "
            "an economics paper by American economists Carmen Reinhart and Kenneth Rogoff "
            "published in a non peer-reviewed issue of the American Economic Review in 2010. "
            "Politicians, commentators, and activists widely cited the paper in political debates "
            "over the effectiveness of austerity in fiscal policy for debt-burdened economies. "
            "The paper argues that when \"gross external debt reaches 60 percent of GDP\", a "
            "country's annual growth declined by two percent, and \"for levels of external debt in "
            "excess of 90 percent\" GDP growth was \"roughly cut in half.\" Appearing in the "
            "aftermath of the 2008 financial crisis, the evidence for the 90%-debt threshold "
            "hypothesis provided support for pro-austerity policies. In 2013, academic critics "
            "accused Reinhart and Rogoff of employing methodology that suffered from 3 major "
            "errors; they asserted that the underlying data did not support the authors' "
            "conclusions. These critics held that the Reinhart–Rogoff paper had led to "
            "unjustified adoption of austerity policies for countries with various levels of "
            "public debt. Further papers by Rogoff and Reinhart, and the International Monetary "
            "Fund, which were not found to contain similar errors, found much lower impact on GDP "
            "growth. The threshold hypothesis retains adherents as well as critics, who suggest "
            "that the thresholds in the relation between public debt and economic growth lack "
            "robustness, so a consensus on the 90%-threshold hypothesis in the relation between "
            "public debt and economic growth has been elusive. A 2022 meta-analysis was unable to "
            "reject the null hypothesis after controlling for publication bias."
        ),
        positions=(
            (
                "Carmen Reinhart and Kenneth Rogoff",
                "When gross external debt reaches 60 percent of GDP annual growth declines by two "
                "percent, and above 90 percent of GDP growth is roughly cut in half.",
            ),
            (
                "Politicians, commentators, and activists",
                "The Reinhart–Rogoff paper supports the effectiveness of austerity in fiscal policy "
                "for debt-burdened economies.",
            ),
            (
                "Academic critics (2013)",
                "The paper's methodology suffered from three major errors and the underlying data did "
                "not support its conclusions, so it led to unjustified adoption of austerity "
                "policies.",
            ),
            (
                "Further papers by Rogoff and Reinhart, and the International Monetary Fund",
                "Debt has a much lower impact on GDP growth than the original paper found.",
            ),
            (
                "Adherents of the threshold hypothesis",
                "The 90% debt threshold in the relation between public debt and economic growth "
                "holds.",
            ),
            (
                "Critics of the threshold hypothesis",
                "The thresholds in the relation between public debt and economic growth lack "
                "robustness.",
            ),
            (
                "A 2022 meta-analysis",
                "The null hypothesis could not be rejected after controlling for publication bias.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-3cd54d04",
        kind="reportage",
        source=(
            "I before E except after C"
        ),
        url=(
            "https://en.wikipedia.org/?curid=838491"
        ),
        text=(
            "\"I before E, except after C\" is a mnemonic rule of thumb for English spelling. If "
            "one is unsure whether a word is spelled with the digraph ⟨ei⟩ or ⟨ie⟩, the rhyme "
            "suggests that the correct order is ⟨ie⟩ unless the preceding letter is ⟨c⟩, in which "
            "case it may be ⟨ei⟩. The rhyme is very well known; Edward Carney calls it \"this "
            "supreme, and for many people solitary, spelling rule\". However, the short form "
            "quoted above has many common exceptions; for example: ⟨ie⟩ after ⟨c⟩: species, "
            "science, sufficient, society ⟨ei⟩ not preceded by ⟨c⟩: seize, vein, weird, heist, "
            "their, feisty, foreign, protein, weigh, neighbor However, some of the words listed "
            "above do not contain the ⟨ie⟩ or ⟨ei⟩ digraph, but the letters ⟨i⟩ (or digraph ⟨ci⟩) "
            "and ⟨e⟩ pronounced separately. The rule is sometimes taught as being restricted "
            "based on the sound represented by the spelling. Two common restrictions are: "
            "excluding cases where the spelling represents the \"long a\" sound (the lexical sets "
            "of FACE and perhaps SQUARE ). This is commonly expressed by continuing the rhyme \"or "
            "when sounding like A, as in neighbor or weigh\". including only cases where the "
            "spelling represents the \"long e\" sound (the lexical sets of FLEECE and perhaps NEAR "
            "and happY ). Variant pronunciations of some words (such as heinous and neither) "
            "complicate application of sound-based restrictions, which do not eliminate all "
            "exceptions. Many authorities deprecate the rule as having too many exceptions to be "
            "worth learning."
        ),
        positions=(
            (
                "Edward Carney",
                "The 'I before E, except after C' rule is a supreme and, for many people, solitary "
                "spelling rule.",
            ),
            (
                "The rhyme / the rule as commonly taught",
                "Spell the digraph as ie unless the preceding letter is c, in which case it may be "
                "ei.",
            ),
            (
                "Some teachers of the rule",
                "The rule should be restricted by sound, applying only to the 'long e' sound.",
            ),
            (
                "Common extension of the rhyme",
                "The rule excludes cases sounding like 'long a', as in neighbor or weigh.",
            ),
            (
                "Many authorities",
                "The rule has too many exceptions to be worth learning.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-9838df26",
        kind="reportage",
        source=(
            "Indictment and arrest of Julian Assange"
        ),
        url=(
            "https://en.wikipedia.org/?curid=60479942"
        ),
        text=(
            "In 2012, while on bail, Julian Assange was granted political asylum in the "
            "Ecuadorian Embassy in London, where he sought to avoid extradition to Sweden, and "
            "what his supporters said was the possibility of subsequent extradition to the US. On "
            "11 April 2019, Ecuador revoked his asylum, he was arrested for failing to appear in "
            "court, and carried out of the embassy by members of the London Metropolitan Police. "
            "Following his arrest, he was charged and convicted, on 1 May 2019, of violating the "
            "Bail Act, and sentenced to fifty weeks in prison. While in prison the US revealed a "
            "previously sealed 2018 US indictment in which Assange was charged with conspiracy to "
            "commit computer intrusion related to his involvement with Chelsea Manning and "
            "WikiLeaks. On 23 May 2019, a US grand jury added 17 espionage charges also related "
            "to his involvement with Chelsea Manning, making a total of 18 federal charges "
            "against Assange in the US. On 25 June 2020 a new indictment was filed alleging that "
            "since 2009, Assange had attempted to recruit hackers and system administrators at "
            "conferences around the world and conspired with hackers including members of LulzSec "
            "and Anonymous. The new indictment described Assange's alleged efforts to recruit "
            "system administrators, Assange and WikiLeaks' role in helping Edward Snowden flee "
            "the US, and their use of Snowden as a recruitment tool, and WikiLeaks' exploiting a "
            "vulnerability in the United States Congress' system to access and publish the "
            "Congressional Research Service reports. Assange's defenders have responded to U.S. "
            "accusations, describing him as a journalist who did nothing more than publish leaked "
            "information that embarrassed the U.S. government. While there was support from some "
            "American journalism institutions and from bi-partisan politicians for Assange's "
            "arrest and indictment, several non-government organisations for press freedom "
            "condemned it. The New York Times's editorial board warned that \"The administration "
            "has begun well by charging Mr. Assange with an indisputable crime. But there is "
            "always a risk with this administration — one that labels the free press as “the "
            "enemy of the people” — that the prosecution of Mr. Assange could become an assault "
            "on the First Amendment and whistle-blowers.\" The case was dismissed in June 2024 "
            "after Assange pleaded guilty to a charge of “conspiracy to obtain and disclose "
            "national defence information” as part of a plea deal which, due to time already "
            "served, resulted in his release from prison."
        ),
        positions=(
            (
                "Assange's supporters",
                "Assange feared that asylum-seeking avoidance of Sweden could lead to subsequent "
                "extradition to the US.",
            ),
            (
                "The US government (grand jury and indictments)",
                "Assange committed computer intrusion conspiracy and espionage offences, including "
                "recruiting hackers and system administrators and helping Edward Snowden flee.",
            ),
            (
                "Assange's defenders",
                "Assange is a journalist who merely published leaked information that embarrassed the "
                "US government.",
            ),
            (
                "Some American journalism institutions and bi-partisan politicians",
                "Assange's arrest and indictment were warranted.",
            ),
            (
                "Several non-government press freedom organisations",
                "The arrest and indictment of Assange should be condemned.",
            ),
            (
                "The New York Times editorial board",
                "Charging Assange with an indisputable crime was a good start, but the prosecution "
                "risks becoming an assault on the First Amendment and whistle-blowers.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-8115ac6b",
        kind="reportage",
        source=(
            "Plebgate"
        ),
        url=(
            "https://en.wikipedia.org/?curid=37304745"
        ),
        text=(
            "\"Plebgate\" (also known as \"Plodgate\" and \"Gategate\") was a British political scandal "
            "which started in September 2012. The trigger was an altercation between Conservative "
            "MP and Chief Whip Andrew Mitchell and police officers on duty outside Downing Street "
            "in London. Leaked police logs, later apparently backed up by eyewitness evidence, "
            "suggested that Mitchell had sworn at police officers and called them \"plebs\" (a "
            "pejorative word meaning someone of low social class) when they refused to open the "
            "main gate for him as he attempted to leave with his bicycle, telling him to walk "
            "through the adjacent pedestrian gate instead. Mitchell apologised, stating that he "
            "had used bad language but denied using the words claimed and in particular calling "
            "police officers \"plebs\". However, finding his position untenable amid intense media "
            "scrutiny, he resigned from the post of Chief Whip a month later. The story returned "
            "to the headlines a few months later when CCTV footage threw into doubt the police "
            "version of events. Further, evidence originally included an email from a member of "
            "the public confirming the police's story. It was revealed this email was actually "
            "sent by a serving police officer who had not been present at the scene. The "
            "Metropolitan Police investigated the incident as Operation Alice. The affair was "
            "revisited again in October 2013, after a report from the Independent Police "
            "Complaints Commission (IPCC) concluded that three officers had given a false account "
            "of a meeting they had with Mitchell at his constituency office in October 2012, and "
            "that the findings of a subsequent investigation had been changed just in time to "
            "recommend no disciplinary action be taken against them. After Home Secretary Theresa "
            "May and Prime Minister David Cameron criticised the conduct of the officers "
            "involved, the officers issued a statement in which they apologised for misleading "
            "the public. At the Old Bailey, PC Keith Wallis subsequently admitted falsely "
            "claiming to have witnessed the incident. He was sentenced to 12 months in prison. "
            "Once the criminal trials had concluded, Mitchell sued The Sun for libel and lost. "
            "The judge ruled on the balance of probabilities that Mitchell had said \"the words "
            "alleged or something so close to them as to amount to the same including the "
            "politically toxic word pleb.\""
        ),
        positions=(
            (
                "Police officers on duty / leaked police logs",
                "Mitchell swore at officers and called them \"plebs\" when they refused to open the "
                "main gate for his bicycle.",
            ),
            (
                "Andrew Mitchell",
                "He used bad language but did not say the words claimed, in particular not \"plebs\".",
            ),
            (
                "Theresa May and David Cameron",
                "The conduct of the officers involved was wrong.",
            ),
            (
                "The three officers",
                "They apologised for misleading the public.",
            ),
            (
                "Independent Police Complaints Commission (IPCC)",
                "Three officers gave a false account of their meeting with Mitchell, and the later "
                "investigation's findings were changed to recommend no disciplinary action.",
            ),
            (
                "The judge in Mitchell's libel case against The Sun",
                "On the balance of probabilities, Mitchell said the alleged words or something so "
                "close as to amount to the same, including \"pleb\".",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-93bd818b",
        kind="reportage",
        source=(
            "Shoot-to-kill policy in Northern Ireland"
        ),
        url=(
            "https://en.wikipedia.org/?curid=2358082"
        ),
        text=(
            "During the Troubles in Northern Ireland, British security forces were accused by "
            "some of operating a \"shoot-to-kill\" policy, under which suspected paramilitary "
            "members were killed without an attempt being made to arrest them. This alleged "
            "policy was claimed to be most frequently directed against suspected members of Irish "
            "republican paramilitary organisations, such as the Provisional Irish Republican Army "
            "(IRA), Official Irish Republican Army (OIRA) and Irish National Liberation Army "
            "(INLA). According to a 1985 inquiry by a team of international lawyers titled Shoot "
            "to Kill?, undercover security force units were \"trained to shoot to kill even where "
            "killing is not legally justifiable and where alternative tactics could and should be "
            "used.\" The British government, including the Northern Ireland Office, consistently "
            "denied that there was ever a \"shoot-to-kill\" policy, stating that \"like everyone "
            "else, the security forces must obey the law and are answerable to the courts for "
            "their actions.\" Notable incidents where a \"shoot-to-kill\" policy was alleged to have "
            "been used include the Loughgall ambush, ambush at Drumnakilly, Coagh ambush, Clonoe "
            "ambush and Operation Flavius. These incidents were all operations carried out by the "
            "security forces against the IRA and INLA, and resulted in 21 Irish republican "
            "paramilitaries being killed. Other notable incidents involving civilian deaths "
            "include the 7 August 1974 killing of an unarmed Catholic farmer (Patrick McElhone, "
            "aged 24) who was taken from his home outside of Pomeroy, County Tyrone and shot dead "
            "by a British Army patrol, found years later by a coroner to be \"unjustified\"; the "
            "death of Fergal Caraher, who was fatally shot by a Royal Marine at a checkpoint; and "
            "the killings of Karen Reilly and Martin Peake, who allegedly drove through a British "
            "Army checkpoint at high speed, with one soldier, Lee Clegg, subsequently being tried "
            "for the shootings. The killing of Ulster Volunteer Force (UVF) member Brian Robinson "
            "by undercover British soldiers is notable for being the most prominent of the very "
            "few alleged \"shoot-to-kill\" incidents where the victim was an Ulster loyalist."
        ),
        positions=(
            (
                "Some who accused British security forces",
                "British security forces operated a 'shoot-to-kill' policy, killing suspected "
                "paramilitaries without attempting arrest.",
            ),
            (
                "1985 international lawyers' inquiry (Shoot to Kill?)",
                "Undercover security force units were trained to shoot to kill even where killing is "
                "not legally justifiable and alternative tactics could and should be used.",
            ),
            (
                "The British government, including the Northern Ireland Office",
                "There was never a 'shoot-to-kill' policy; the security forces must obey the law and "
                "are answerable to the courts.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-63a4e346",
        kind="reportage",
        source=(
            "The Life and Opinions of Tristram Shandy, Gentleman"
        ),
        url=(
            "https://en.wikipedia.org/?curid=302768"
        ),
        text=(
            "The Life and Opinions of Tristram Shandy, Gentleman, often known simply as Tristram "
            "Shandy, is a humorous novel by Laurence Sterne. It was published from 1759 to 1767, "
            "in nine volumes across five instalments. The novel purports to be a memoir, but the "
            "titular Tristram is an effusive and digressive narrator who begins the story with "
            "his conception and does not reach a description of his birth until the third volume. "
            "While attempting to explain four accidents in his early life which have doomed him "
            "to an unhappy future, Tristram describes domestic conflicts between his irritable "
            "father Walter and his gentle Uncle Toby, and inserts humorous discourses on a range "
            "of intellectual topics. Stylistically, Sterne is influenced by the earlier satirists "
            "Alexander Pope, Jonathan Swift, Rabelais, and Cervantes. The novel is characterised "
            "by innuendo, especially sexual double entendre and aposiopesis (unfinished "
            "sentences). Sterne burlesques serious writers and genres, particularly parodying "
            "Robert Burton's The Anatomy of Melancholy and the genre of consolatio. The novel is "
            "also remembered for surprising visual elements, such as blank, black, and marbled "
            "pages; entire paragraphs censored with asterisks; and inserted diagrams. Tristram "
            "Shandy was Sterne's first novel, and immediately transformed his life from that of "
            "an obscure rural clergyman to that of a literary celebrity. Eighteenth century "
            "audiences expressed some reservations about its daring and bawdy humour, especially "
            "given Sterne's religious profession, but praised its originality and its moments of "
            "sentimental morality. Over time, it has been an influential novel with a mixed "
            "reputation: Victorian audiences criticised it as obscene, but modernist and "
            "postmodernist authors embraced it in the twentieth century. Adaptations include the "
            "2006 film A Cock and Bull Story, starring Steve Coogan and Rob Brydon as they "
            "metafictionally struggle to make the film."
        ),
        positions=(
            (
                "Eighteenth century audiences",
                "Tristram Shandy's daring and bawdy humour is questionable, especially given Sterne's "
                "religious profession, but its originality and sentimental morality deserve praise.",
            ),
            (
                "Victorian audiences",
                "Tristram Shandy is obscene.",
            ),
            (
                "Modernist and postmodernist authors",
                "Tristram Shandy is a novel worth embracing.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-96ce9d7d",
        kind="reportage",
        source=(
            "Traingate"
        ),
        url=(
            "https://en.wikipedia.org/?curid=51401290"
        ),
        text=(
            "Traingate is the popular name given to a 2016 disputed incident between Jeremy "
            "Corbyn, leader of the British Labour Party, and the train operating company Virgin "
            "Trains East Coast (VTEC) and its minority shareholder Richard Branson. During August "
            "2016, a video was released of Corbyn sitting on the floor of a VTEC train while "
            "campaigning during a leadership challenge by Owen Smith. Corbyn said the train was "
            "\"ram-packed\" and used this to support his policy to reverse the 1990s privatisation "
            "of the railways of Great Britain, which created private operators such as VTEC. "
            "Controversy developed when Virgin released CCTV images a week later appearing to "
            "show Corbyn walking past available seats, leading to accusations that the incident "
            "had been staged for political gain, which Corbyn denied, saying, \"Yes, I did walk "
            "through the train. Yes, I did look for two empty seats together so I could sit down "
            "with my wife, to talk to her. That wasn't possible so I went to the end of the "
            "train.\" Reactions were mixed, with commentators finding both support and damage for "
            "all sides involved. Analysis of the CCTV footage was later done by a media outlet "
            "paid by the reelection bid of Jeremy Corbyn in the then-Labour leadership contest. "
            "This showed that the unreserved seats in some of the images were occupied and that "
            "other passengers also sat in the vestibules."
        ),
        positions=(
            (
                "Jeremy Corbyn",
                "The train was ram-packed, he looked for two empty seats to sit with his wife, found "
                "none and so sat on the floor at the end of the train; the incident was not staged.",
            ),
            (
                "Corbyn (campaign use of the incident)",
                "The crowded train supports reversing the 1990s privatisation of Britain's railways.",
            ),
            (
                "Virgin Trains East Coast (VTEC)",
                "CCTV images appear to show Corbyn walking past available seats, suggesting the "
                "incident was staged.",
            ),
            (
                "Critics of Corbyn",
                "The incident had been staged for political gain.",
            ),
            (
                "Media outlet paid by Corbyn's reelection bid",
                "The CCTV footage shows the unreserved seats were occupied and other passengers also "
                "sat in the vestibules.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-bde3990c",
        kind="reportage",
        source=(
            "Trophy hunting"
        ),
        url=(
            "https://en.wikipedia.org/?curid=1913249"
        ),
        text=(
            "Trophy hunting is a form of hunting for sport in which parts of the hunted wild "
            "animals are kept and displayed as trophies. The animal being targeted, known as the "
            "\"game\", is typically a mature male specimen from a popular species of collectable "
            "interests, usually of large sizes, holding impressive horns, antlers, furs, or "
            "manes. Most trophies consist of only select parts of the animal, which are prepared "
            "for display by a taxidermist. The parts most commonly kept vary by species but often "
            "include the head, hide, tusks, horns, or antlers. Trophies are often displayed in "
            "trophy rooms or game rooms, or in gun rooms along with the hunter's gun collection. "
            "Trophy hunting has strong supporters and opponents. The controversy focuses on the "
            "morality of hunting for pleasure rather than for practical use, as well as questions "
            "about the extent to which big-game hunting benefits conservation efforts."
        ),
        positions=(
            (
                "strong supporters of trophy hunting",
                "Trophy hunting is acceptable and big-game hunting benefits conservation efforts.",
            ),
            (
                "opponents of trophy hunting",
                "Hunting for pleasure rather than for practical use is immoral, and big-game hunting "
                "does not clearly benefit conservation.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-c5918549",
        kind="reportage",
        source=(
            "U.S. Army Corps of Engineers civil works controversies"
        ),
        url=(
            "https://en.wikipedia.org/?curid=13772684"
        ),
        text=(
            "The United States Army Corps of Engineers (USACE) is involved in a wide range of "
            "public works projects, including environmental protection, water supply, recreation, "
            "flood damage and reduction, beach nourishment, homeland security, military "
            "construction, and support for other government agencies. It currently manages 740 "
            "dams across the United States and Puerto Rico. Across 12 Flood Control Acts, "
            "beginning with the first on March 1, 1917, Congress has authorized the Corps of "
            "Engineers to participate in flood protection and damage reduction in almost every "
            "state. USACE projects are either specifically authorized by Congress or fall under a "
            "Congressionally authorized category. With projects carried out in all fifty states, "
            "local citizens, special interest groups, and political organizations may lobby "
            "Congress for authorization and funding of specific projects in their areas. These "
            "groups may also oppose some or all aspects of a USACE project. Many civil works "
            "projects undertaken by USACE have been criticized as being riddled with patronage or "
            "a waste of resources. Examples include the New Madrid Floodway Project and the flood "
            "protection systems in New Orleans. Some projects have been described as relying on "
            "flawed or manipulated analyses during the planning phase. Certain projects have also "
            "been criticized for causing significant environmental damage or for providing "
            "limited economic benefits, such as the Mississippi River–Gulf Outlet in southeast "
            "Louisiana. Faulty design and substandard construction have been cited as "
            "contributing factors in the failure of levees following Hurricane Katrina. Former "
            "U.S. Senators Russ Feingold and John McCain have advocated for reforming the Corps' "
            "approach. Holding the Corps accountable has also been supported by the group "
            "Levees.Org, led by Sandy Rosenthal. However, some observers argue that a key "
            "difficulty in implementing changes has been the political process itself. Whether "
            "USACE planners and engineers can achieve optimal outcomes within the constraints of "
            "the direction they receive remains part of ongoing debate."
        ),
        positions=(
            (
                "Critics of USACE civil works projects",
                "Many Corps projects are riddled with patronage or are a waste of resources, with "
                "some relying on flawed or manipulated planning analyses.",
            ),
            (
                "Critics of certain USACE projects (e.g., Mississippi River–Gulf Outlet)",
                "Some projects cause significant environmental damage or provide limited economic "
                "benefits.",
            ),
            (
                "Those citing causes of the post-Katrina levee failures",
                "Faulty design and substandard construction contributed to the levee failures.",
            ),
            (
                "Former Senators Russ Feingold and John McCain",
                "The Corps' approach should be reformed.",
            ),
            (
                "Levees.Org, led by Sandy Rosenthal",
                "The Corps should be held accountable.",
            ),
            (
                "Some observers",
                "A key difficulty in implementing changes has been the political process itself.",
            ),
            (
                "Local citizens, special interest groups, and political organizations",
                "They may lobby Congress for authorization and funding of specific projects in their "
                "areas.",
            ),
            (
                "Local citizens, special interest groups, and political organizations (opposing "
                "groups)",
                "They may oppose some or all aspects of a USACE project.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="rep-346f9dd9",
        kind="reportage",
        source=(
            "Yucca Mountain Johnny"
        ),
        url=(
            "https://en.wikipedia.org/?curid=5370813"
        ),
        text=(
            "Yucca Mountain Johnny is a cartoon miner created by the United States Department of "
            "Energy (DOE) to present information to children on nuclear waste disposal and the "
            "Yucca Mountain Project. Serving as the virtual guide for the DOE's Youth Zone web "
            "site and appearing \"live-action\" in Nevada schools, Yucca Mountain Johnny has drawn "
            "harsh criticism as a propaganda tool. Former U.S. Representative Shelley Berkley "
            "(D-NV) called Yucca Mountain Johnny \"the Department of Energy's Joe Camel\", a "
            "reference to a cartoon mascot for the tobacco industry which drew criticism for "
            "targeting children. Former Representative Jon Porter (R-NV) stated that \"to sell the "
            "Yucca Mountain Project to our children through the use of a cartoon character is an "
            "irresponsible and desperate act.\" DOE spokesperson Craig Stevens, however, defended "
            "Yucca Mountain Johnny, arguing that it \"teaches hydrology, geology, and earth "
            "science\", and that it is \"part of our duty to explain to the public what we're "
            "doing.\" Support for Yucca Mountain Johnny was present in the House of "
            "Representatives, with Representative Joe Barton (R-TX) stating that \"nobody "
            "questions the accuracy or truth of what's on the Web site\", and Representative David "
            "Hobson (R-OH) stating that it \"may have a place in teaching kids.\" Berkley, who is a "
            "vocal opponent of a Yucca Mountain waste repository, attempted to add an amendment "
            "to an energy spending bill that would have prevented the funds from being used for "
            "the DOE Youth Zone web site. The amendment was defeated, 271–147. The Youth Zone now "
            "appears to have been removed from the DOE's website, although copies of the site can "
            "be found via the Wayback Machine."
        ),
        positions=(
            (
                "Shelley Berkley",
                "Yucca Mountain Johnny is the Department of Energy's Joe Camel, a propaganda tool "
                "targeting children, and funds for the Youth Zone web site should be blocked.",
            ),
            (
                "Jon Porter",
                "Selling the Yucca Mountain Project to children through a cartoon character is an "
                "irresponsible and desperate act.",
            ),
            (
                "Craig Stevens (DOE spokesperson)",
                "Yucca Mountain Johnny teaches hydrology, geology, and earth science, and explaining "
                "the DOE's work to the public is part of its duty.",
            ),
            (
                "Joe Barton",
                "Nobody questions the accuracy or truth of what is on the Web site.",
            ),
            (
                "David Hobson",
                "Yucca Mountain Johnny may have a place in teaching kids.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-8cc6408d",
        kind="dialogue",
        source=(
            "Animal Welfare Strategy"
        ),
        url=(
            "https://hansard.parliament.uk/debates/FF465BD6-6501-4DF6-8FC8-E7167E34C733"
        ),
        text=(
            "Emma Reynolds: I thank the hon. Gentleman, on behalf of the whole House, for what he "
            "has just said, and for his service, before he became a Member and since. This is a "
            "really important area, and we absolutely appreciate that the Veterinary Surgeons Act "
            "needs updating. I can reassure him that we are continuing to pursue opportunities to "
            "do that. Josh Newbury: All I want for Christmas is a generational boost to animal "
            "welfare. That does not have the same ring to it as what the queen of Christmas sang, "
            "but given the widespread public support for animal welfare, maybe we could give her "
            "a run for her money with that one. Our British farmers lead the way globally on high "
            "standards of farmed animal welfare, and they deserve great credit for that. Can the "
            "Secretary of State confirm that the animal welfare strategy will continue that "
            "trend, and will work with farmers and their representatives, so that they can reap "
            "the rewards, and so that domestic production is safeguarded as we move towards "
            "higher standards? Emma Reynolds: I can confirm that. As I said earlier, measures are "
            "already in place to provide funding to farmers to help them improve animal welfare "
            "standards. Those measures include veterinary visits to help them continue to improve "
            "their animal welfare standards. Mr Speaker: I call the Father of the House. Sir "
            "Edward Leigh: We have some of the best animal welfare standards for farm animals in "
            "the world. Of course, we can do much by regulation, but the best way to protect farm "
            "animals is to have contented and prosperous family farmers who love their animals "
            "and care for them. When I arrived in the House, farmers used to talk in glowing "
            "terms about Tom Williams, the Labour Minister for agriculture in the Attlee "
            "Government, who started 80 years of prosperity for our farmers. I beg the Secretary "
            "of State and the Minister, if they are really concerned about animal welfare and the "
            "welfare of our farmers, to drop the absurd family farm tax."
        ),
        positions=(
            (
                "Emma Reynolds (Secretary of State)",
                "The Veterinary Surgeons Act needs updating and the government is pursuing "
                "opportunities to do so.",
            ),
            (
                "Emma Reynolds (Secretary of State)",
                "The animal welfare strategy will work with farmers, and existing funding and "
                "veterinary visits already help farmers improve welfare standards.",
            ),
            (
                "Josh Newbury",
                "British farmers lead the world on farmed animal welfare, and the animal welfare "
                "strategy should work with them so domestic production is safeguarded as standards "
                "rise.",
            ),
            (
                "Sir Edward Leigh",
                "Britain has some of the best farm animal welfare standards, which are best protected "
                "by contented, prosperous family farmers, so the government should drop the 'absurd "
                "family farm tax'.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-5d28ff22",
        kind="dialogue",
        source=(
            "Inheritance Tax"
        ),
        url=(
            "https://hansard.parliament.uk/debates/685175FA-3561-4C37-98BA-68F8C020D44E"
        ),
        text=(
            "Wendy Morton: A wealth of small businesses across my constituency keeps our local "
            "economy growing. Does my hon. Friend agree that at a time when our businesses need "
            "support that will enable them to create employment for the next generation, this "
            "Government—on whose Benches there is, of course, no business experience—are just "
            "squeezing and squeezing our businesses out of business? Andrew Griffith: My right "
            "hon. Friend is quite right. I urge every Member of this House to spend time with "
            "family businesses in their constituency; there are excellent organisations such as "
            "Family Business UK that would be delighted to make the introduction. My right hon. "
            "Friend is also absolutely right about the relative dearth on the Government Benches "
            "of business and private sector experience and of an understanding of how the economy "
            "works. However, that is capable of remediation, if only Government Ministers and "
            "Members were to seek to educate themselves on the benefits to their constituencies "
            "and constituents of family businesses. We Conservatives will not let a spiteful, "
            "prejudiced Labour party destroy those family businesses, which is why we will— "
            "Gareth Snell: Will the hon. Gentleman give way? Andrew Griffith: I would be "
            "delighted to give way and for the hon. Member to talk about the family business "
            "contribution in his own constituency, and why he will therefore be supporting the "
            "Opposition motion this afternoon. Gareth Snell: There are many wonderful family "
            "businesses in Stoke-on-Trent, not least Potclays, which makes clay for the pottery "
            "industry. The hon. Gentleman talks about this spiteful tax; he will know that it was "
            "introduced in 1986 under Mrs Thatcher. Did he think it was a spiteful tax when she "
            "introduced it?"
        ),
        positions=(
            (
                "Wendy Morton",
                "The Government, which she says has no business experience, is squeezing small and "
                "family businesses out of business when they need support to create jobs.",
            ),
            (
                "Andrew Griffith",
                "Government Members lack business and private sector experience, and the Labour party "
                "is spiteful and prejudiced in threatening family businesses, which Conservatives "
                "will defend.",
            ),
            (
                "Andrew Griffith",
                "Members should spend time with family businesses in their constituencies and support "
                "the Opposition motion.",
            ),
            (
                "Gareth Snell",
                "The tax Griffith calls spiteful was introduced in 1986 under Mrs Thatcher, so the "
                "criticism is inconsistent.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-3ce7dd93",
        kind="dialogue",
        source=(
            "Climate Change"
        ),
        url=(
            "https://hansard.parliament.uk/debates/E430E896-E5B0-497B-9B28-DFE20B961745"
        ),
        text=(
            "Dr Chambers: Will the Minister join me in congratulating Lib Dem-run Winchester city "
            "council on its fantastic initiative, Solar Together, which installs solar panels on "
            "council houses? So far, it has installed solar panels on 35 properties, reducing "
            "energy bills, lifting people out of fuel poverty and reducing carbon output. What "
            "support is the Minister giving to ensure that such initiatives can continue, in "
            "Winchester and throughout the whole country? Katie White: I will absolutely "
            "congratulate Winchester city council on leading on this. Councils play a hugely "
            "important role, and I am looking forward to meeting many of them to discuss this "
            "issue when I visit the Local Government Association later this week. We have £1 "
            "billion of funding for community energy projects, and we are bringing forward more "
            "measures to accelerate progress, because this really is an opportunity to tackle the "
            "climate crisis, bring down energy bills and contribute to energy security. Richard "
            "Burgon: I commend the Minister and the team on their approach. Tackling climate "
            "change needs to be a national and international effort. We should all be pulling "
            "together on this goal. Is it not time to call out some of the Opposition parties and "
            "their friends in the right-wing media for engaging in a propaganda wave of climate "
            "change denial? That poses a real risk to our future jobs, economy, fuel security and "
            "way of life. Katie White: I thank my hon. Friend, who has raised this issue on many "
            "occasions in this House, and who is a friend of mine from across our great city. It "
            "is really important that we work at international, national and local level. Across "
            "our country, we all have a responsibility for the words and phrases that we use, and "
            "a responsibility to tackle misinformation and be honest about the challenges. That "
            "is not to say that we cannot disagree, but we could do so far more agreeably."
        ),
        positions=(
            (
                "Dr Chambers",
                "Winchester city council's Solar Together scheme, which puts solar panels on council "
                "houses, is a fantastic initiative that cuts bills, fuel poverty and carbon output, "
                "and ministers should support such initiatives continuing nationwide.",
            ),
            (
                "Katie White (Minister)",
                "Councils play an important role in clean energy; the government is backing it with "
                "£1 billion for community energy projects and further measures to tackle the climate "
                "crisis, cut bills and improve energy security.",
            ),
            (
                "Richard Burgon",
                "Climate action should be a united national and international effort, and Opposition "
                "parties and right-wing media promoting climate change denial should be called out as "
                "a risk to jobs, the economy, fuel security and way of life.",
            ),
            (
                "Katie White (Minister)",
                "Everyone has a responsibility to be honest, avoid misinformation and use careful "
                "language on climate, though disagreement is acceptable if conducted more agreeably.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-630a14df",
        kind="dialogue",
        source=(
            "Continuity of Care in the NHS"
        ),
        url=(
            "https://hansard.parliament.uk/debates/4EFD47E5-FD1E-4A4C-BFA6-E2505400A6DF"
        ),
        text=(
            "Maya Ellis: Continuity of care in maternity services is based on women building "
            "relationships with maternity practitioners who meet them where they are. I would "
            "like to echo the comments of the hon. Member for North Shropshire (Helen Morgan): "
            "many obstetricians and midwives have been truly disappointed at comments from an NHS "
            "leader yesterday, who argued that more maternity units should be shut and that only "
            "consolidation of services can make births safer. Women in this country will not "
            "accept the industrialisation of our bodies. This Labour Government have promised "
            "neighbourhood and preventive healthcare, which has to include allowing new mums to "
            "feel rooted in the communities where they will go through their biggest physical and "
            "psychological change. Can the Minister assure me that our bodies will not be treated "
            "like a manufacturing supply chain to be optimised as she develops the asks for "
            "maternity services in this country? Dame Diana Johnson: Gosh, my hon. Friend made a "
            "very passionate statement there, and I absolutely agree with what she said. This "
            "work will be undertaken with the national maternity and neonatal taskforce, and we "
            "will look at all these issues. I hope my hon. Friend will feel able to contribute to "
            "that work if she wishes to. Mr Speaker: I call the shadow Minister. Dr Caroline "
            "Johnson: Continuity of care is desirable but not always possible, and in "
            "circumstances where it is not, a single patient record offers an opportunity to "
            "improve care, but it also brings the risk of unauthorised access to notes. We have "
            "seen recent high-profile cases where notes have been accessed that should not have "
            "been. That has led to people across the country worrying that this issue could "
            "affect them personally in less high-profile cases and about what will happen when "
            "the single patient record will be available nationally. How are the Government going "
            "to protect patient confidentiality? Mr Speaker: Order. It is a struggle to get from "
            "the original question to where we are, but the Minister is happy to answer."
        ),
        positions=(
            (
                "Maya Ellis",
                "Continuity of care depends on women building relationships with practitioners, and "
                "maternity units should not be closed or consolidated in a way that treats women's "
                "bodies like an industrial supply chain.",
            ),
            (
                "An NHS leader (as reported by Maya Ellis)",
                "More maternity units should be shut, because only consolidation of services can make "
                "births safer.",
            ),
            (
                "Obstetricians and midwives (as reported by Maya Ellis)",
                "They are disappointed at the NHS leader's comments.",
            ),
            (
                "Dame Diana Johnson",
                "She agrees with Maya Ellis, and the issues will be examined with the national "
                "maternity and neonatal taskforce, to which Ellis is invited to contribute.",
            ),
            (
                "Dr Caroline Johnson",
                "Continuity of care is desirable but not always possible, and a single patient record "
                "could improve care but risks unauthorised access to notes, so the Government must "
                "say how it will protect patient confidentiality.",
            ),
            (
                "Mr Speaker",
                "The shadow Minister's question strays far from the original question, though the "
                "Minister is willing to answer it.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-508a9d5b",
        kind="dialogue",
        source=(
            "Domestic Animals: Welfare"
        ),
        url=(
            "https://hansard.parliament.uk/debates/CA7CAAAB-9400-4A41-AAEE-F2EB4434AC22"
        ),
        text=(
            "Linsey Farnsworth: Sticking with the theme of cats, my office was recently alerted "
            "to a rather troubling incident involving a cat whose owner had been taken into "
            "hospital unexpectedly, and no one was able to access the flat. It took many days for "
            "the police to obtain a warrant, and meanwhile all the RSPCA was able to do was post "
            "ice and food through the letterbox to keep the cat alive. Animals should not be left "
            "to suffer in those circumstances. Will the Minister consider granting the RSPCA "
            "limited powers of entry in order to rescue animals faster, without delays caused by "
            "constraints on police time and resources? Dame Angela Eagle: I am sorry to hear "
            "about the trauma related to my hon. Friend’s constituent. We recognise the RSPCA’s "
            "vital role in promoting animal welfare, but we do not have plans to extend statutory "
            "enforcement powers at this stage. Such powers are normally reserved for public "
            "bodies that have formal lines of accountability. We want to ensure that any future "
            "approach maintains clear oversight while preserving the RSPCA’s important charitable "
            "and advocacy functions. Lisa Smart: One of the topics that constituents get in touch "
            "with me about a lot, particularly over the autumn, is the impact that fireworks can "
            "have on domestic animals—both the number and volume of displays and kids deploying "
            "fireworks in the street or their back gardens. Those cause distress to animals, and "
            "also to people who have suffered trauma or have served as veterans. I urge the "
            "Department to look at limiting the volume of fireworks or restricting their use "
            "solely to licensed displays. Dame Angela Eagle: We are aware of the welfare issues "
            "around fireworks, and we are looking at the evidence to see whether any such changes "
            "would actually make a difference."
        ),
        positions=(
            (
                "Linsey Farnsworth",
                "Animals should not be left to suffer while police seek warrants, so the RSPCA should "
                "be granted limited powers of entry to rescue animals faster.",
            ),
            (
                "Dame Angela Eagle (Minister)",
                "The government recognises the RSPCA's vital role but has no plans to extend "
                "statutory enforcement powers, which are normally reserved for publicly accountable "
                "bodies.",
            ),
            (
                "Lisa Smart",
                "The Department should limit the volume of fireworks or restrict their use solely to "
                "licensed displays because of the distress they cause animals and traumatised people "
                "or veterans.",
            ),
            (
                "Dame Angela Eagle (Minister)",
                "The government is aware of the welfare issues around fireworks and is looking at the "
                "evidence on whether changes would make a difference.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-37efe89a",
        kind="dialogue",
        source=(
            "Food Welfare Labelling"
        ),
        url=(
            "https://hansard.parliament.uk/debates/E34F71ED-37FF-4179-9346-7EC7E26BFD7B"
        ),
        text=(
            "Sam Rushworth: 7. Whether she has made an assessment of the potential merits of "
            "improving the transparency of food welfare labelling. The Minister for Food Security "
            "and Rural Affairs: As set out in our welfare strategy, we are working with the "
            "farming and food industry, vets and scientists to explore how improved animal "
            "welfare labelling could improve consumer transparency, support farmers and promote "
            "better animal welfare. Sam Rushworth: I like to buy British, because I know that our "
            "farmers have some of the best quality and welfare standards in the world, and I know "
            "that my constituents feel the same. However, that is difficult when everything is "
            "labelled with Union flags and fake farm names. May I invite the Minister to meet "
            "with members of the Labour Rural Research Group to discuss honest food labelling, "
            "which we are campaigning for? Dame Angela Eagle: I am happy to meet the rural "
            "research group to talk about these important issues, but under UK food labelling "
            "rules, food that is not of UK origin cannot be labelled with a British flag, and if "
            "the primary ingredient is not British, it cannot be labelled as such without "
            "pointing out that the primary ingredient is not British. If my hon. Friend has any "
            "examples of where that is happening, I would like to see them. Andrew George: Of "
            "course, it is not only Labour Members who are concerned about this issue, so I hope "
            "the Minister would be prepared to meet a cross-party group of MPs. The problem we "
            "face in this country is not just the use of the Union Jack; there is a high risk "
            "that we are sucking in imports that do not meet the animal welfare standards we have "
            "in this country, which even now we are rightly seeking to improve."
        ),
        positions=(
            (
                "The Minister for Food Security and Rural Affairs",
                "The government is working with industry, vets and scientists to explore how improved "
                "animal welfare labelling could improve transparency, support farmers and promote "
                "welfare.",
            ),
            (
                "Sam Rushworth",
                "British food labelling is misleading because of Union flags and fake farm names, and "
                "honest food labelling is needed so buyers of British produce can trust it.",
            ),
            (
                "Dame Angela Eagle",
                "Existing UK labelling rules already bar non-UK food from carrying a British flag and "
                "require disclosure if the primary ingredient is not British, and she will meet the "
                "rural research group and wants to see any examples of breaches.",
            ),
            (
                "Andrew George",
                "The concern is cross-party, so the Minister should meet a cross-party group, and the "
                "greater risk is imports that fail UK animal welfare standards.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-ba1a2553",
        kind="dialogue",
        source=(
            "High Street Businesses: Tax Changes"
        ),
        url=(
            "https://hansard.parliament.uk/debates/5AA1A445-7CCE-4B5C-A9C7-18E3EE86EC2A"
        ),
        text=(
            "Sir Ashley Fox: 2. What assessment she has made of the potential impact of changes "
            "to business rates announced in the autumn Budget 2025 on the retail, hospitality and "
            "leisure sectors. Wendy Chamberlain: 6. What assessment she has made of the potential "
            "impact of tax changes on high street businesses. Dr Danny Chambers: 13. What "
            "assessment she has made of the potential impact of tax changes on high street "
            "businesses. The Exchequer Secretary to the Treasury: On business rates, the "
            "Government have announced a support package for all businesses worth £4.3 billion "
            "over the next three years. We have introduced permanently lower multipliers for "
            "eligible retail, hospitality and leisure businesses, including those on the high "
            "street. In addition, every pub and live music venue will get 15% off its new bill "
            "from April. The Government will also bring forward a high streets strategy later "
            "this year. Sir Ashley Fox: Many retail, hospitality and tourism businesses in my "
            "constituency traditionally give young people their first job, but with the "
            "Chancellor’s jobs tax, the unemployment rights Act and now huge increases in rates, "
            "many of those businesses are struggling to survive, so they just cannot afford to "
            "take on those young people. Does the Minister accept that his Government are the "
            "reason that youth unemployment is now higher in the UK than in the EU for the first "
            "time since records began?"
        ),
        positions=(
            (
                "The Exchequer Secretary to the Treasury (the Government)",
                "The Government's £4.3 billion business rates support package, permanently lower "
                "multipliers for retail, hospitality and leisure, 15% off bills for pubs and live "
                "music venues, and a forthcoming high streets strategy support high street "
                "businesses.",
            ),
            (
                "Sir Ashley Fox",
                "The Chancellor's jobs tax, the employment rights Act and large rates increases are "
                "leaving retail, hospitality and tourism businesses unable to afford to hire young "
                "people, making the Government responsible for youth unemployment being higher in the "
                "UK than in the EU.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-2225a4b9",
        kind="dialogue",
        source=(
            "Immigration and Asylum Bill (Ninth sitting)"
        ),
        url=(
            "https://hansard.parliament.uk/debates/529b3c81-37f0-4ac9-b84d-46ceeaa45ca7"
        ),
        text=(
            "Ben Goldsborough: That gets to the crux of the issue that we are trying to combat "
            "within the Bill. The issue itself is not necessarily the principles behind the ECHR; "
            "it is the over-interpretation—the juridification—of the law. What we are seeking to "
            "do through the Bill, which my constituents greatly welcome, is rein in the courts "
            "and make them understand that Parliament sets the rules of the game. We will ensure "
            "that they are firm but fair for all residents, as well as for those stuck on waiting "
            "lists who need swift action. Anna Turley: My hon. Friend is absolutely right. That "
            "is the crux of the Bill: ensuring that we define matters for courts so that we do "
            "not see the free-for-all of over-interpretation that we have seen before. I see this "
            "as a binary choice: reform the ECHR and have greater control over our borders, or "
            "leave and lose our ability to return illegal migrants and foreign criminals. I "
            "choose the powers that the ECHR gives us, which protect our individual rights and "
            "freedom. Matt Vickers: The Minister talked about Winston Churchill. Does she think "
            "that Winston Churchill would have desired legislation that allows people who are "
            "categorically a threat to our national security, or a danger to the community, to "
            "stay in this country? Anna Turley: I would put that back to the hon. Gentleman and "
            "ask whether he thinks that Winston Churchill would have desired the British state to "
            "seek to remove people to places where they will face almost certain death, torture "
            "and war. Matt Vickers: The clause relates to people who are too dangerous to "
            "lawfully stay in the country. It is not giving us a perspective by which to remove "
            "those people. Those people are a danger to our community—you are saying that they "
            "are a danger to our community and a threat to our national security—yet we are not "
            "going far enough to remove them. It undermines the entire clause."
        ),
        positions=(
            (
                "Ben Goldsborough",
                "The problem is not the ECHR's principles but the courts' over-interpretation "
                "(juridification) of the law, so the Bill should rein in the courts and make clear "
                "that Parliament sets the rules.",
            ),
            (
                "Anna Turley",
                "The Bill should define matters for courts to prevent over-interpretation, and the "
                "choice is binary: reform the ECHR to gain greater border control, or leave and lose "
                "the ability to return illegal migrants and foreign criminals; she chooses the powers "
                "the ECHR gives.",
            ),
            (
                "Matt Vickers",
                "The clause does not go far enough because it covers people too dangerous to lawfully "
                "stay yet gives no means to remove them, which undermines the whole clause.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-5c33b7ca",
        kind="dialogue",
        source=(
            "Immigration and Asylum Bill (Seventh sitting)"
        ),
        url=(
            "https://hansard.parliament.uk/debates/5f8a9237-3b28-4009-badb-b5a324683796"
        ),
        text=(
            "Tom Gordon: Will the financial independence test be individualised, will it be "
            "evidence-based in its assessment, and will it recognise barriers such as credit "
            "history, references and guarantors? Furthermore, will a survivor’s use of refuge or "
            "public funds to escape abuse count against them? Anna Turley: I thank the hon. "
            "Gentleman for his questions and I will say a lot more about those issues when I "
            "respond to the contributions by the hon. Member for Brighton Pavilion. However, we "
            "are absolutely clear that we are not going to penalise people for experiencing "
            "hardship. These reforms preserve protections for vulnerable people and children, but "
            "it is vital that we make it clear that immigration control and the wider public "
            "interest should be given proper weight in any consideration. This is about restoring "
            "balance, not removing safeguards. That is critical. Mr Jonathan Brash: Having "
            "listened to some contributions, particularly from the hon. Member for Brighton "
            "Pavilion, I think that most fair-minded people would be concerned that these reforms "
            "could have a detrimental impact on children. Can the Minister confirm whether or not "
            "these reforms remove protections for children? Anna Turley: My hon. Friend raises a "
            "critical issue that is, of course, dear to all of our hearts. Again, I will say more "
            "about it later, but these reforms absolutely do not remove protections for children. "
            "The best interests of children will continue to remain a primary consideration in "
            "immigration decision making, as they should be. The reforms in clause 19 ensure that "
            "children’s interests are considered alongside other important factors, including "
            "compliance with immigration law and the wider public interest in maintaining an "
            "effective immigration system. Tom Gordon: Will the Minister give way?"
        ),
        positions=(
            (
                "Tom Gordon",
                "The financial independence test should be individualised and evidence-based, "
                "recognise barriers such as credit history, references and guarantors, and not count "
                "a survivor's use of refuge or public funds against them.",
            ),
            (
                "Anna Turley (Minister)",
                "The reforms will not penalise people for experiencing hardship and preserve "
                "protections for vulnerable people and children, while giving proper weight to "
                "immigration control and the wider public interest; this restores balance rather than "
                "removing safeguards.",
            ),
            (
                "Anna Turley (Minister)",
                "The reforms do not remove protections for children; their best interests remain a "
                "primary consideration, weighed alongside compliance with immigration law and the "
                "wider public interest.",
            ),
            (
                "Mr Jonathan Brash",
                "Most fair-minded people would be concerned that the reforms could harm children.",
            ),
            (
                "The hon. Member for Brighton Pavilion (as characterised by Brash)",
                "The reforms could have a detrimental impact on children.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-9e862155",
        kind="dialogue",
        source=(
            "Immigration and Asylum Bill (Sixth sitting)"
        ),
        url=(
            "https://hansard.parliament.uk/debates/a3fc3ad1-11aa-44df-8605-a384565e96f9"
        ),
        text=(
            "Melanie Onn: The hon. Lady says that this is not a way to reform the system. Does "
            "she have any ideas about the kinds of reform that she would be ready to accept? Siân "
            "Berry: I have said that, based on my own casework, my experience of the Home "
            "Office’s errors, and the cases that I have seen, I would like to see investment in "
            "Home Office decision making to make it better in the first place. That would be the "
            "best way to deal with this issue, particularly when more than half of appeals are "
            "being approved. Melanie Onn: I thank the hon. Lady for giving way once again. Given "
            "the number of amendments she has tabled—the point being that she will not support "
            "any element of change whatsoever—I gently and respectfully suggest that she is "
            "actually very happy with the system as it is, she is happy to accept all the "
            "evidence from a huge industry that exists to support immigrants, migrants, refugees "
            "and asylum seekers, and she does not want any reform whatsoever other than throwing "
            "the system open even further. Siân Berry: It is pretty clear that I think the Bill "
            "is a result of the Government responding to toxic rhetoric coming from other "
            "parties, and that it is an attempt to be seen to be doing something. Blake "
            "Stephenson: Will the hon. Member give way?"
        ),
        positions=(
            (
                "Siân Berry",
                "Reform should come through investing in Home Office decision making so decisions are "
                "right in the first place, especially since more than half of appeals are approved.",
            ),
            (
                "Siân Berry",
                "The Bill is the Government's response to toxic rhetoric from other parties and an "
                "attempt to be seen to be doing something.",
            ),
            (
                "Melanie Onn",
                "Berry's many amendments show she will accept no change and is happy with the current "
                "system, relying on evidence from a huge industry supporting migrants and asylum "
                "seekers, and wants it thrown open even further.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-2d4bf7a6",
        kind="dialogue",
        source=(
            "Immigration and Asylum Bill (Tenth sitting)"
        ),
        url=(
            "https://hansard.parliament.uk/debates/b5a3b022-a478-48e9-b17e-639252e77934"
        ),
        text=(
            "Siân Berry: Will the Minister give way? Anna Turley: I was going to mention work and "
            "study, but I will come back to that. Siân Berry: My question is more about the "
            "revenue and its spending. We have heard from local authorities concerned that they "
            "might have higher costs as a result of the measures. Can the Minister give us any "
            "reassurance that the costs will not spill over into services that might be affected "
            "by some of the things in the impact assessment? Anna Turley: The hon. Lady makes an "
            "important point, but I do not see that the implications will fall on local "
            "authorities. As I said, in the course of publishing regulations as a result of the "
            "passage of the Bill, we will explore the mechanisms for bringing the money in and "
            "for where it will go in the Exchequer. However, at this point I do not want to "
            "commit to any undertakings to local authorities. The measure is about ensuring that "
            "people contribute and pay their fair share. The hon. Lady mentioned work—we share "
            "that commitment. We all want to see those who have come here fleeing persecution "
            "move as quickly as possible into work and into contributing to this country. That is "
            "why our new work and study routes will allow people to get off core protection, off "
            "dependency and as quickly as possible into the work and study routes that we will "
            "provide and encourage asylum seekers to use. Mr Kohler: I wish to make two swift "
            "points about what the Minister has just said. First, does the tax system not allow "
            "people to contribute—is that not the whole point? When people are integrated, they "
            "contribute via the tax system. Othering refugees because they came to us as refugees "
            "strikes me as completely the wrong approach, and one that we do not apply to other "
            "forms of state help. Secondly, I am no doubt being obtuse here, but can the Minister "
            "point me to the consequences for non-payment? I am still not clear on that."
        ),
        positions=(
            (
                "Siân Berry",
                "Local authorities fear higher costs from the measures, and the Minister should "
                "reassure that costs will not spill over into services affected by the impact "
                "assessment.",
            ),
            (
                "Anna Turley (Minister)",
                "The implications will not fall on local authorities, and she will not commit to "
                "undertakings to them; the measure ensures people pay their fair share, with "
                "mechanisms set out in regulations after the Bill passes.",
            ),
            (
                "Anna Turley (Minister)",
                "The new work and study routes should move those fleeing persecution off core "
                "protection and dependency and into work and contributing to the country.",
            ),
            (
                "Mr Kohler",
                "The tax system already lets integrated refugees contribute, so singling out refugees "
                "for payment is the wrong approach and not applied to other forms of state help.",
            ),
            (
                "Mr Kohler",
                "It is unclear what the consequences of non-payment are.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-c5c028c5",
        kind="dialogue",
        source=(
            "Neurodivergent Pupils: Mainstream Schools"
        ),
        url=(
            "https://hansard.parliament.uk/debates/796D437F-605E-4658-8D43-F8EF764BDCCE"
        ),
        text=(
            "Juliet Campbell: 8. What steps her Department is taking to improve educational "
            "outcomes for neurodivergent pupils in mainstream schools. The Minister for School "
            "Standards: We are determined that our schools be inclusive for all children, "
            "including those with neurodivergence. The work undertaken by our neurodivergence "
            "task-and-finish group has informed our proposed reforms to the special educational "
            "needs and disabilities system, including the national inclusion standard and the "
            "investment in continuous professional development and teacher training. Juliet "
            "Campbell: I thank the Minister for her reply. Sixty-five per cent of teacher "
            "training providers say that new teachers are not equipped to support SEND pupils in "
            "mainstream schools, with too many teachers still leaving training without the skills "
            "and confidence to support neurodivergent children, including those with dyslexia. "
            "Will the Minister consider reforming the initial training requirements so that every "
            "trainee educator is able to demonstrate practical competency in identifying and "
            "supporting neurodivergent children before achieving their qualified teacher status? "
            "Georgia Gould: I thank my hon. Friend for her ongoing thoughtful work on this issue, "
            "which has very much informed our thinking. We have strengthened SEND content in the "
            "initial teacher training and early career framework, with Ofsted reporting that SEND "
            "is well integrated in that initial training. However, we do want to go further, and "
            "SEND will be a core focus for the 2027 review, as well as the £200 million we are "
            "investing into teacher training on special educational needs and disabilities. "
            "Alison Bennett: For some neurodivergent children, mainstream school is not a place "
            "where they can succeed. One such child is Livvi, who is 14. Following autistic "
            "burnout and a period of not being in education, education otherwise than at school "
            "has been an absolute godsend for her, but her amazing mum, Carrie, is worried about "
            "the Government’s proposed changes to EOTAS provision. Carrie is coming to Parliament "
            "this evening; when I meet her, what should I say about whether people who have "
            "fought for their kids, like her, will get a say in what future EOTAS provision looks "
            "like?"
        ),
        positions=(
            (
                "The Minister for School Standards",
                "Schools should be inclusive for all children including neurodivergent ones, and the "
                "government's proposed SEND reforms (national inclusion standard, investment in CPD "
                "and teacher training), informed by the neurodivergence task-and-finish group, will "
                "deliver this.",
            ),
            (
                "Juliet Campbell",
                "New teachers are not adequately equipped to support neurodivergent and SEND pupils, "
                "so initial training requirements should be reformed to require demonstrated "
                "practical competency before qualified teacher status.",
            ),
            (
                "Georgia Gould",
                "SEND content in initial teacher training and the early career framework is already "
                "strengthened and well integrated, but the government will go further through the "
                "2027 review and £200 million of investment in SEND teacher training.",
            ),
            (
                "Alison Bennett",
                "Mainstream school does not work for some neurodivergent children, EOTAS has been "
                "vital for children like Livvi, and families like Carrie's should get a say in future "
                "EOTAS provision.",
            ),
            (
                "Carrie (Livvi's mother)",
                "She is worried about the government's proposed changes to EOTAS provision.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-460fe9ba",
        kind="dialogue",
        source=(
            "Police Officer Numbers"
        ),
        url=(
            "https://hansard.parliament.uk/debates/090BA51D-8D94-4A5F-8976-56564C75E847"
        ),
        text=(
            "Sir John Whittingdale: 13. What estimate her Department has made of the number of "
            "police officers in September (a) 2024 and (b) 2025. The Minister for Policing and "
            "Crime: In England and Wales, there were 145,550 full-time equivalent police officers "
            "as of September 2025 and 146,868 police officers as of September 2024. This "
            "Government are focused on putting officers where the public expect to see them: back "
            "on the frontline, keeping our communities safe. We have already delivered more than "
            "3,100 additional police officers and police community support officers into "
            "neighbourhood roles. Sir John Whittingdale: The Minister has confirmed that under "
            "this Government the number of police officers has fallen. It is now proposed that in "
            "Essex they will become part of a regional force that will be more remote and less "
            "accountable to the people that they serve. How does that increase public confidence "
            "in policing? Sarah Jones: As part of our measures to tackle antisemitism, this "
            "morning we have announced funding for an additional 500 police officers in areas "
            "where we need them most, which I am sure that Members across the House will welcome. "
            "The right hon. Gentleman asks about forces. As he will know, a review is currently "
            "being undertaken by Lord Bernard Hogan-Howe, who is looking at both local policing "
            "units and regional-level units, as well as the national police service, which we "
            "will be introducing. Luke Myer: I welcome the 48 new neighbourhood officers and "
            "policy community support officers who have joined Cleveland police in the last year, "
            "but I want to see an overhaul of the national police funding formula to support the "
            "Cleveland area. The Policing Minister has committed to do that, but can she clarify "
            "the timeline for when we will see the formula changed and more officers back on our "
            "streets again?"
        ),
        positions=(
            (
                "The Minister for Policing and Crime (Sarah Jones)",
                "The Government are putting officers back on the frontline, having delivered over "
                "3,100 additional officers and PCSOs into neighbourhood roles, and are funding 500 "
                "more officers to tackle antisemitism.",
            ),
            (
                "Sir John Whittingdale",
                "Police officer numbers have fallen under this Government, and moving Essex into a "
                "more remote, less accountable regional force would not increase public confidence in "
                "policing.",
            ),
            (
                "Luke Myer",
                "The national police funding formula should be overhauled to support Cleveland, and "
                "he wants a timeline for the change so more officers are back on the streets.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-0863c16c",
        kind="dialogue",
        source=(
            "Pupils with SEND: Mainstream Schools"
        ),
        url=(
            "https://hansard.parliament.uk/debates/1D5D48E5-58BE-4539-B613-71059E23E6FA"
        ),
        text=(
            "Aphra Brandreth: Following a recent visit to Tushingham-with-Grindley primary "
            "school, the headteacher raised concerns with me that for many small, rural schools "
            "like Tushingham and Shocklach Oviatt, the new inclusion fund does not compensate for "
            "the impact of changes to the school’s block funding. Not every child with SEND needs "
            "one-to-one support, but many need teaching assistants and other staff to help them "
            "regulate, access learning and benefit from targeted support. If school budgets are "
            "being squeezed, it is often that support that ends up being reduced. How will the "
            "Minister ensure that the funding changes do not inadvertently reduce the support "
            "that children with SEND need to thrive in mainstream schools? Georgia Gould: The "
            "reforms do not fully come in until 2030, so the extra money through the inclusive "
            "mainstream fund sits alongside investment through the current system and education, "
            "health and care plans. Once the reforms are fully in place, there will be more money "
            "going directly into schools. The inclusive mainstream fund is to build up funding in "
            "the meantime. Schools will also benefit from the Experts at Hand service, which is "
            "putting £1.8 billion into specialists. Sonia Kumar: Dudley cannot afford to lose "
            "another generation of young people to unemployment, exclusion or missed opportunity. "
            "The rate of our young people not in education, employment or training was recognised "
            "in Alan Milburn’s review. Local leaders at my February NEETs roundtable were clear: "
            "alternative provision for children with SEND is desperately needed. Dudley college "
            "has brought forward a credible plan. Will the Minister recognise the urgency and "
            "back children in Dudley by approving the plan? Georgia Gould: I thank my hon. Friend "
            "for her leadership on that critical issue. As the Secretary of State said, we are "
            "investing £3.7 billion into new specialist places. I will meet her to discuss the "
            "specific school she raises. Mr Speaker: I call the shadow Minister."
        ),
        positions=(
            (
                "Aphra Brandreth",
                "The new inclusion fund does not compensate small rural schools for the impact of "
                "block funding changes, and squeezed budgets tend to cut the teaching assistant and "
                "other support children with SEND need.",
            ),
            (
                "Georgia Gould",
                "The reforms do not fully come in until 2030, the inclusive mainstream fund builds up "
                "funding in the meantime alongside current investment, and more money will go "
                "directly into schools, backed by £1.8 billion for Experts at Hand specialists.",
            ),
            (
                "Sonia Kumar",
                "Dudley needs alternative provision for children with SEND urgently, and the Minister "
                "should approve Dudley college's plan.",
            ),
            (
                "Georgia Gould (on Dudley)",
                "The government is investing £3.7 billion in new specialist places, and she will meet "
                "Sonia Kumar to discuss the specific school raised.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-5080c918",
        kind="dialogue",
        source=(
            "UN Framework Convention on International Tax Co-operation: Global Taxes"
        ),
        url=(
            "https://hansard.parliament.uk/debates/5DB3E549-829A-44FE-BC29-B2B05FEFEBBF"
        ),
        text=(
            "Iqbal Mohamed: 1. Whether he has had discussions with the Chancellor of the "
            "Exchequer on global taxes on oil and gas companies in the context of the proposed UN "
            "framework convention on international tax co-operation. The Minister for Energy: "
            "This is a matter for the Treasury, although we remain closely engaged. The UN "
            "framework convention is focused on improving effective and inclusive international "
            "tax co-operation, not on creating specific global taxes on oil and gas companies. "
            "Iqbal Mohamed: The combined market value of the six big oil super-majors has soared "
            "by more than $130 billion since the first US-Israeli attack on Iran, while my "
            "constituents and those across the country face higher bills. Will the Energy "
            "Secretary and the Government work with international partners to establish global "
            "taxes on the fossil fuel industry through the UN tax convention and help bill payers "
            "with their energy costs? Michael Shanks: As I said, this is a matter for the "
            "Treasury, but we look closely at where we can co-operate around the world. This "
            "country’s windfall tax has raised £12 billion, funding public services and "
            "supporting the hon. Gentleman’s constituents and many others with the cost of "
            "living. We will continue to invest in bringing down bills, but we will also invest "
            "in the infrastructure that gets us off fossil fuels."
        ),
        positions=(
            (
                "Iqbal Mohamed",
                "The Government should work with international partners to establish global taxes on "
                "the fossil fuel industry through the UN tax convention, because oil super-majors' "
                "market value has soared while bill payers face higher bills.",
            ),
            (
                "The Minister for Energy (Michael Shanks)",
                "Global oil and gas taxes are a matter for the Treasury, and the UN convention is "
                "about effective, inclusive international tax co-operation rather than creating "
                "specific global taxes on oil and gas companies.",
            ),
            (
                "The Minister for Energy (Michael Shanks)",
                "The UK's windfall tax has raised £12 billion for public services and cost-of-living "
                "support, and the Government will keep investing in bringing down bills and in "
                "infrastructure to move off fossil fuels.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-597fe3d5",
        kind="dialogue",
        source=(
            "Venture Capital Trust Income Tax Relief"
        ),
        url=(
            "https://hansard.parliament.uk/debates/81307A3D-7E2A-43C3-BE97-72B5D8AD9480"
        ),
        text=(
            "Alan Mak: 9. What assessment she has made of the potential impact of reducing "
            "up-front venture capital trust income tax relief on VCT fundraising. The Economic "
            "Secretary to the Treasury: At the Budget, the Government announced a comprehensive "
            "package of entrepreneurship tax measures, designed to provide substantially enhanced "
            "support for scaling businesses across the UK. That includes doubling the maximum "
            "amount that a company can raise through the enterprise investment scheme and the "
            "venture capital trust scheme. Overall, the changes to those schemes are forecast to "
            "generate about £100 million per year of additional investment in high-growth, "
            "scaling companies, thanks to the increased scheme limits in the Budget. Alan Mak: A "
            "recent industry survey revealed that 62% of VCT founders are scaling back growth "
            "plans, 45% are cutting headcounts, and 25% are leaving the country. Will the "
            "Government reverse the Chancellor’s plans to cut this relief, or will her legacy for "
            "Britain’s tech sector be lower growth, fewer jobs and lasting damage? Rachel Blake: "
            "Absolutely not; we have real confidence in the British venture capital sector. In "
            "the 2025 Budget, we doubled the investment limits and gross assets threshold for the "
            "enterprise investment and venture capital trust schemes. Those changes are "
            "supporting growth and development. Mr Speaker: I call the shadow Minister."
        ),
        positions=(
            (
                "The Economic Secretary to the Treasury (Government)",
                "The Budget's entrepreneurship tax measures, including doubling EIS and VCT limits, "
                "will provide substantially enhanced support and generate about £100 million a year "
                "of additional investment in scaling companies.",
            ),
            (
                "Alan Mak",
                "Cutting up-front VCT income tax relief is damaging the tech sector, causing founders "
                "to scale back, cut jobs and leave the country, and the Government should reverse it.",
            ),
            (
                "Rachel Blake",
                "The Government will not reverse the changes; it has real confidence in the British "
                "venture capital sector, and the doubled limits are supporting growth and "
                "development.",
            ),
        ),
    ),
    PastedMaterialCase(
        case_id="dia-543ea338",
        kind="dialogue",
        source=(
            "Welfare Budget"
        ),
        url=(
            "https://hansard.parliament.uk/debates/8F175112-C2F9-4D40-8FCC-12039ADD3655"
        ),
        text=(
            "John Lamont: 4. What estimate he has made of what the total welfare budget will be "
            "at the end of this Parliament. The Minister for Social Security and Disability: In "
            "March, the Office for Budget Responsibility published its official forecast, "
            "predicting that at the end of the current Parliament, in 2029-30, UK welfare "
            "spending will be about £390 billion. The OBR will update that forecast in the "
            "Budget, which will take place on Wednesday fortnight. John Lamont: The Minister has "
            "just confirmed that the benefits bill will continue to grow. He also seems to have "
            "confirmed the Prime Minister’s position that national security “cannot come at the "
            "expense of social security.” —[ Official Report , 9 September 2026; Vol. 790, c. "
            "1036.] Is that correct? Sir Stephen Timms: The hon. Member will be relieved to know "
            "that spending on working-age adults’ and children’s welfare is forecast to be 4.9% "
            "of GDP at the end of the current Parliament, as it is now. Overall welfare spending "
            "is forecast to rise by less than half as much in this Parliament as in the last, by "
            "just over 0.3 percentage points by 2030-31 compared with 0.7 percentage points in "
            "the last Parliament. This Government are putting right the problems that they "
            "inherited. Deirdre Costigan: According to a recent report from the Good Growth "
            "Foundation, 50% of disability claimants would swap up to £1,000 of benefits for help "
            "such as employment support, therapy and physical aids. Does the Minister agree that "
            "giving disabled people tailored support could both reduce the welfare bill and stop "
            "those who want to work being written off by the system?"
        ),
        positions=(
            (
                "The Minister for Social Security and Disability (Sir Stephen Timms)",
                "Welfare spending is on track to grow far more slowly this Parliament than the last, "
                "with working-age and children's welfare holding at 4.9% of GDP, and the Government "
                "is fixing inherited problems.",
            ),
            (
                "John Lamont",
                "The Minister's forecast confirms the benefits bill will keep growing, which "
                "contradicts the Prime Minister's claim that national security cannot come at the "
                "expense of social security.",
            ),
            (
                "Deirdre Costigan",
                "Giving disabled people tailored support such as employment help, therapy and aids "
                "could both cut the welfare bill and stop those who want to work being written off.",
            ),
        ),
    ),
)

